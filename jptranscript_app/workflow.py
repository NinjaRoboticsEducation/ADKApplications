"""
Local transcript workflow runner.

This module owns the heavy lifting for the product:

- input resolution
- chunked local-model processing
- artifact-backed stage outputs
- deterministic validation and repair
- final HTML generation and save
"""

from __future__ import annotations

import os
import pathlib
import re
from collections import Counter
from dataclasses import dataclass
from functools import lru_cache
from typing import Callable
from typing import Optional

import requests

from .tools.beautifier_tools import apply_design_template
from .tools.furigana_tools import auto_add_furigana
from .tools.furigana_tools import refine_furigana
from .tools.furigana_tools import validate_furigana
from .tools.html_converter import convert_to_html
from .tools.text_processing import APP_DIR
from .tools.text_processing import DEFAULT_CHUNK_SIZE
from .tools.text_processing import DEFAULT_OVERLAP_CHARS
from .tools.text_processing import JobPaths
from .tools.text_processing import MIN_CHUNK_SIZE
from .tools.text_processing import PipelineError
from .tools.text_processing import TextChunk
from .tools.text_processing import build_markdown_toc
from .tools.text_processing import chunk_text_with_metadata
from .tools.text_processing import collapse_meaningless_japanese_spacing
from .tools.text_processing import detect_input_text
from .tools.text_processing import extract_markdown_headings
from .tools.text_processing import initialize_manifest
from .tools.text_processing import make_job_paths
from .tools.text_processing import normalize_text
from .tools.text_processing import protect_timestamps
from .tools.text_processing import reassemble_chunks
from .tools.text_processing import restore_timestamps
from .tools.text_processing import save_html_file
from .tools.text_processing import slugify_filename
from .tools.text_processing import strip_markdown_toc
from .tools.text_processing import validate_glossary
from .tools.text_processing import validate_optimization
from .tools.text_processing import validate_paragraph
from .tools.text_processing import write_manifest


PROMPTS_DIR = APP_DIR / "prompts"
TOTAL_STAGES = 7
STAGE_METADATA: dict[str, tuple[int, str]] = {
    "optimization": (1, "Optimization"),
    "paragraph": (2, "Paragraph Structuring"),
    "furigana": (3, "Furigana Annotation"),
    "refinement": (4, "Furigana Refinement"),
    "glossary": (5, "Glossary Building"),
    "html": (6, "HTML Conversion"),
    "beautify": (7, "HTML Beautification"),
}

GENERIC_HEADING_STOPWORDS = {
    "皆さん",
    "こんにちは",
    "今日",
    "今回",
    "日本語",
    "ポッドキャスト",
    "友達",
    "問題",
    "答え",
    "先生",
    "景色",
    "写真",
    "言葉",
    "意味",
    "紹介",
    "本日",
}


@dataclass(frozen=True)
class PipelineResult:
    job_id: str
    output_path: pathlib.Path
    manifest_path: pathlib.Path
    source_type: str
    source_label: str
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class ProgressUpdate:
    """Structured progress update emitted while the pipeline is running."""

    stage: str
    status: str
    message: str
    stage_index: int = 0
    stage_total: int = TOTAL_STAGES
    completed: Optional[int] = None
    total: Optional[int] = None
    job_id: Optional[str] = None


ProgressCallback = Optional[Callable[[ProgressUpdate], None]]


class OllamaChatClient:
    """Small, explicit client for local Ollama chat calls."""

    def __init__(
        self,
        *,
        model: Optional[str] = None,
        api_base: Optional[str] = None,
        num_ctx: int = 8192,
        temperature: float = 0.2,
        timeout_seconds: int = 180,
        keep_alive: str = "20m",
    ) -> None:
        self.model = model or os.getenv("JPTRANSCRIPT_MODEL", "gemma4-agent")
        self.api_base = (
            api_base
            or os.getenv("OLLAMA_API_BASE", "http://localhost:11434")
        ).rstrip("/")
        self.num_ctx = int(os.getenv("JPTRANSCRIPT_NUM_CTX", str(num_ctx)))
        self.temperature = float(
            os.getenv("JPTRANSCRIPT_TEMPERATURE", str(temperature))
        )
        self.timeout_seconds = int(
            os.getenv("JPTRANSCRIPT_TIMEOUT_SECONDS", str(timeout_seconds))
        )
        self.keep_alive = os.getenv("JPTRANSCRIPT_KEEP_ALIVE", keep_alive)

    def chat(self, system_prompt: str, user_prompt: str) -> str:
        payload = {
            "model": self.model,
            "stream": False,
            "keep_alive": self.keep_alive,
            "options": {
                "num_ctx": self.num_ctx,
                "temperature": self.temperature,
            },
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }
        try:
            response = requests.post(
                f"{self.api_base}/api/chat",
                json=payload,
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            raise PipelineError(
                "Could not reach Ollama. Make sure `ollama serve` is running and "
                f"the model `{self.model}` is available. Original error: {exc}"
            ) from exc

        data = response.json()
        content = data.get("message", {}).get("content", "")
        if not content or not content.strip():
            raise PipelineError(
                f"Ollama returned an empty response for model `{self.model}`."
            )
        return normalize_text(content)


@lru_cache(maxsize=None)
def _load_prompt(name: str) -> str:
    return (PROMPTS_DIR / name).read_text(encoding="utf-8").strip()


def run_transcript_pipeline(
    user_input: str,
    *,
    client: Optional[OllamaChatClient] = None,
    progress_callback: ProgressCallback = None,
) -> PipelineResult:
    """Run the full local transcript pipeline and return the saved HTML path."""
    transcript_text, source_type, source_label = detect_input_text(user_input)
    model_client = client or OllamaChatClient()
    job_paths = make_job_paths()
    manifest = initialize_manifest(
        job_paths,
        source_type=source_type,
        source_label=source_label,
    )
    warnings: list[str] = []

    job_paths.raw_input_path.write_text(transcript_text, encoding="utf-8")
    manifest["last_run_status"] = "running"
    write_manifest(job_paths.manifest_path, manifest)
    _emit_progress(
        progress_callback,
        stage="pipeline",
        status="started",
        message=(
            f"Started transcript build for {source_type} input. "
            f"Job ID: {job_paths.job_id}."
        ),
        job_id=job_paths.job_id,
    )

    current_stage = "pipeline"
    try:
        current_stage = "optimization"
        optimized = _run_optimization_stage(
            transcript_text,
            job_paths=job_paths,
            manifest=manifest,
            client=model_client,
            progress_callback=progress_callback,
        )
        current_stage = "paragraph"
        structured = _run_paragraph_stage(
            optimized,
            job_paths=job_paths,
            manifest=manifest,
            client=model_client,
            progress_callback=progress_callback,
        )
        current_stage = "furigana"
        furigana = _run_furigana_stage(
            structured,
            job_paths=job_paths,
            manifest=manifest,
            progress_callback=progress_callback,
        )
        furigana_report = validate_furigana(furigana)
        if not furigana_report["pass"]:
            warning = (
                "Furigana validation reported less than ideal coverage; the "
                "deterministic output was preserved to avoid dropping content."
            )
            warnings.append(warning)
            _emit_progress(
                progress_callback,
                stage="furigana",
                status="warning",
                message=warning,
                job_id=job_paths.job_id,
            )
        current_stage = "refinement"
        refined = _run_refinement_stage(
            furigana,
            job_paths=job_paths,
            manifest=manifest,
            progress_callback=progress_callback,
        )
        current_stage = "glossary"
        glossary = _run_glossary_stage(
            refined,
            job_paths=job_paths,
            manifest=manifest,
            client=model_client,
            progress_callback=progress_callback,
        )
        current_stage = "html"
        html = _run_html_stage(
            glossary,
            job_paths=job_paths,
            manifest=manifest,
            progress_callback=progress_callback,
        )
        current_stage = "beautify"
        output_path = _run_beautify_stage(
            html,
            structured_markdown=structured,
            job_paths=job_paths,
            manifest=manifest,
            progress_callback=progress_callback,
        )
    except Exception as exc:
        manifest["last_run_status"] = "failed"
        manifest["last_failed_stage"] = current_stage
        manifest["last_error"] = str(exc)
        if current_stage in manifest["stages"]:
            stage_record = dict(manifest["stages"].get(current_stage, {}))
            stage_record["status"] = "failed"
            stage_record["error"] = str(exc)
            manifest["stages"][current_stage] = stage_record
        write_manifest(job_paths.manifest_path, manifest)
        _emit_progress(
            progress_callback,
            stage=current_stage,
            status="failed",
            message=f"{_stage_label(current_stage)} failed: {exc}",
            job_id=job_paths.job_id,
        )
        raise

    manifest["final_output_path"] = str(output_path)
    manifest["last_run_status"] = "completed"
    if warnings:
        manifest["warnings"] = warnings
    write_manifest(job_paths.manifest_path, manifest)

    return PipelineResult(
        job_id=job_paths.job_id,
        output_path=output_path,
        manifest_path=job_paths.manifest_path,
        source_type=source_type,
        source_label=source_label,
        warnings=tuple(warnings),
    )


def _run_optimization_stage(
    text: str,
    *,
    job_paths: JobPaths,
    manifest: dict[str, object],
    client: OllamaChatClient,
    progress_callback: ProgressCallback = None,
) -> str:
    prompt = _load_prompt("optimization.md") + (
        "\n\nPreserve any [[TIMESTAMP:mm:ss]] marker exactly, on its own line, "
        "in the same relative location."
        "\n\nReturn only the cleaned primary text chunk. Do not mention chunk "
        "boundaries or chunk counts."
    )
    protected_text = protect_timestamps(text)
    chunks = chunk_text_with_metadata(
        protected_text,
        max_chars=DEFAULT_CHUNK_SIZE,
        overlap_chars=DEFAULT_OVERLAP_CHARS,
    )
    _mark_stage_running(
        manifest,
        job_paths=job_paths,
        stage_name="optimization",
        message=f"Optimization running with {len(chunks)} chunk(s).",
    )
    _emit_progress(
        progress_callback,
        stage="optimization",
        status="started",
        message=f"[1/7] Optimization started ({len(chunks)} chunk(s)).",
        total=len(chunks),
        job_id=job_paths.job_id,
    )
    outputs: list[str] = []
    chunk_records: list[dict[str, object]] = []

    for chunk in chunks:
        output, report, attempts, fallback = _run_chunk_worker(
            chunk,
            prompt=prompt,
            client=client,
            validator=lambda source, result: validate_optimization(
                restore_timestamps(source),
                collapse_meaningless_japanese_spacing(restore_timestamps(result)),
            ),
            stage_name="optimization",
        )
        restored_output = collapse_meaningless_japanese_spacing(
            restore_timestamps(output)
        )
        outputs.append(restored_output)
        chunk_path = job_paths.stage1_chunks_dir / f"{chunk.chunk_id}.txt"
        chunk_path.write_text(restored_output, encoding="utf-8")
        chunk_records.append(
            {
                **chunk.to_dict(),
                "output_file": str(chunk_path),
                "validation": report,
                "attempts": attempts,
                "fallback_used": fallback,
            }
        )
        if _should_emit_chunk_progress(chunk.index, len(chunks), fallback):
            details = []
            if fallback:
                details.append("fallback safeguards applied")
            elif attempts > 1:
                details.append(f"stabilized after {attempts} attempts")
            detail_suffix = f" ({'; '.join(details)})" if details else ""
            _emit_progress(
                progress_callback,
                stage="optimization",
                status="progress",
                message=(
                    f"[1/7] Optimization chunk {chunk.index}/{len(chunks)} "
                    f"completed{detail_suffix}."
                ),
                completed=chunk.index,
                total=len(chunks),
                job_id=job_paths.job_id,
            )

    optimized = collapse_meaningless_japanese_spacing(
        restore_timestamps(reassemble_chunks(outputs))
    )
    job_paths.stage1_output_path.write_text(optimized, encoding="utf-8")
    manifest["stages"]["optimization"] = {
        "status": "completed",
        "output_file": str(job_paths.stage1_output_path),
        "chunks": chunk_records,
        "validation": validate_optimization(text, optimized),
    }
    write_manifest(job_paths.manifest_path, manifest)
    _emit_progress(
        progress_callback,
        stage="optimization",
        status="completed",
        message="[1/7] Optimization completed.",
        completed=len(chunks),
        total=len(chunks),
        job_id=job_paths.job_id,
    )
    return optimized


def _run_paragraph_stage(
    text: str,
    *,
    job_paths: JobPaths,
    manifest: dict[str, object],
    client: OllamaChatClient,
    progress_callback: ProgressCallback = None,
) -> str:
    prompt = _load_prompt("paragraph.md") + (
        "\n\nPreserve any [[TIMESTAMP:mm:ss]] marker exactly, on its own line, "
        "in the same relative location."
        "\n\nReturn only the cleaned primary text chunk. Do not mention chunk "
        "boundaries or chunk counts."
        "\n\nWhen processing a single chunk, do NOT add a table of contents. "
        "Only add section headings, paragraph breaks, and dialogue formatting. "
        "Return only the structured chunk."
    )
    protected_text = protect_timestamps(text)
    chunks = chunk_text_with_metadata(
        protected_text,
        max_chars=DEFAULT_CHUNK_SIZE,
        overlap_chars=DEFAULT_OVERLAP_CHARS,
    )
    _mark_stage_running(
        manifest,
        job_paths=job_paths,
        stage_name="paragraph",
        message=f"Paragraph structuring running with {len(chunks)} chunk(s).",
    )
    _emit_progress(
        progress_callback,
        stage="paragraph",
        status="started",
        message=f"[2/7] Paragraph structuring started ({len(chunks)} chunk(s)).",
        total=len(chunks),
        job_id=job_paths.job_id,
    )
    body_chunks: list[str] = []
    chunk_records: list[dict[str, object]] = []

    for chunk in chunks:
        output, report, attempts, fallback = _run_chunk_worker(
            chunk,
            prompt=prompt,
            client=client,
            validator=lambda source, result: validate_paragraph(
                restore_timestamps(source),
                _repair_paragraph_document(restore_timestamps(result)),
            ),
            stage_name="paragraph",
            fallback_output=_fallback_paragraph_chunk(chunk.text),
        )
        restored_output = restore_timestamps(output)
        restored_output = strip_markdown_toc(restored_output)
        body_chunks.append(restored_output)
        chunk_path = job_paths.stage2_chunks_dir / f"{chunk.chunk_id}.md"
        chunk_path.write_text(restored_output, encoding="utf-8")
        chunk_records.append(
            {
                **chunk.to_dict(),
                "output_file": str(chunk_path),
                "validation": report,
                "attempts": attempts,
                "fallback_used": fallback,
            }
        )
        if _should_emit_chunk_progress(chunk.index, len(chunks), fallback):
            details = []
            if fallback:
                details.append("fallback structure used")
            elif attempts > 1:
                details.append(f"stabilized after {attempts} attempts")
            detail_suffix = f" ({'; '.join(details)})" if details else ""
            _emit_progress(
                progress_callback,
                stage="paragraph",
                status="progress",
                message=(
                    f"[2/7] Paragraph chunk {chunk.index}/{len(chunks)} "
                    f"completed{detail_suffix}."
                ),
                completed=chunk.index,
                total=len(chunks),
                job_id=job_paths.job_id,
            )

    merged_body = reassemble_chunks(body_chunks).strip()
    repaired = _repair_paragraph_document(merged_body)
    job_paths.stage2_output_path.write_text(repaired, encoding="utf-8")
    manifest["stages"]["paragraph"] = {
        "status": "completed",
        "output_file": str(job_paths.stage2_output_path),
        "chunks": chunk_records,
        "validation": validate_paragraph(text, repaired),
    }
    write_manifest(job_paths.manifest_path, manifest)
    _emit_progress(
        progress_callback,
        stage="paragraph",
        status="completed",
        message="[2/7] Paragraph structuring completed.",
        completed=len(chunks),
        total=len(chunks),
        job_id=job_paths.job_id,
    )
    return repaired


def _repair_paragraph_document(markdown_text: str) -> str:
    body = strip_markdown_toc(markdown_text).strip()
    explicit_title, sections = _extract_sections(body)
    if not sections:
        sections = [("本文", body)]

    repaired_sections: list[str] = []
    headings: list[str] = []
    for index, (heading, content) in enumerate(sections):
        repaired_heading = _repair_section_heading(heading, content, index)
        headings.append(repaired_heading)
        repaired_sections.append(f"## {repaired_heading}\n{content.strip()}".strip())

    title = _derive_document_title(
        explicit_title=explicit_title,
        headings=headings,
        sections=sections,
    )
    toc = build_markdown_toc(headings)
    title_block = f"# {title}\n\n" if title else ""
    body_block = "\n\n".join(repaired_sections).strip()
    return f"{title_block}{toc}\n{body_block}".strip()


def _fallback_paragraph_chunk(text: str) -> str:
    body = restore_timestamps(normalize_text(text))
    return f"## 本文\n{body}".strip()


def _extract_sections(markdown_text: str) -> tuple[Optional[str], list[tuple[str, str]]]:
    body = normalize_text(markdown_text)
    title_match = re.match(r"(?m)^#\s+(.+)$", body)
    explicit_title = _clean_heading_text(title_match.group(1)) if title_match else None
    if title_match:
        body = re.sub(r"(?m)^#\s+.+$\n?", "", body, count=1).strip()

    matches = list(re.finditer(r"(?m)^##\s+(.+)$", body))
    if not matches:
        return explicit_title, []

    sections: list[tuple[str, str]] = []
    for index, match in enumerate(matches):
        heading = match.group(1).strip()
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(body)
        content = body[start:end].strip()
        sections.append((heading, content))
    return explicit_title, sections


def _repair_section_heading(heading: str, content: str, index: int) -> str:
    cleaned = _clean_heading_text(heading)
    if _heading_needs_repair(heading, cleaned, content):
        inferred = _infer_heading_from_section(content, index)
        if inferred:
            return inferred
    return cleaned or _infer_heading_from_section(content, index) or "本文"


def _clean_heading_text(text: str) -> str:
    cleaned = collapse_meaningless_japanese_spacing(
        restore_timestamps(normalize_text(text))
    )
    cleaned = re.sub(r"（[ぁ-ん]+）", "", cleaned)
    cleaned = re.sub(r"\*(\d+)", "", cleaned)
    cleaned = cleaned.replace("【用語】", "")
    cleaned = cleaned.replace("．．．", "")
    cleaned = cleaned.replace("...", "")
    cleaned = re.sub(r"[“”\"'`]+", "", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned)
    cleaned = cleaned.strip(" -:：。．")
    return cleaned


def _heading_needs_repair(raw_heading: str, heading: str, content: str) -> bool:
    first_sentence = _plain_section_text(content).split("。", maxsplit=1)[0].strip()
    is_truncated_sentence_prefix = bool(
        heading and first_sentence.startswith(heading) and len(first_sentence) - len(heading) >= 4
    )
    return (
        not heading
        or heading in {"本文", "セクション", "タイトル未設定"}
        or any(token in raw_heading for token in ("．．．", "...", "…"))
        or heading.endswith("と")
        or len(heading) < 2
        or is_truncated_sentence_prefix
    )


def _plain_section_text(content: str) -> str:
    text = collapse_meaningless_japanese_spacing(
        restore_timestamps(normalize_text(content))
    )
    text = re.sub(r"(?m)^\d{1,2}:\d{2}(?::\d{2})?\s*$", "", text)
    text = re.sub(r"（[ぁ-ん]+）", "", text)
    text = re.sub(r"\*(\d+)", "", text)
    text = text.replace("【用語】", "")
    text = text.replace("【", "").replace("】", "")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _infer_heading_from_section(content: str, index: int) -> str:
    plain = _plain_section_text(content)
    if not plain:
        return "本文"
    plain = re.sub(r"^[^：\n]{1,24}：", "", plain).strip()

    if index == 0 and ("役立つ言葉" in plain or "ご紹介します" in plain):
        return "イントロダクション"
    if "天気" in plain and ("今日" in plain or "明日" in plain):
        return "天気の話"
    if "こんにちは" in plain and ("ポッドキャスト" in plain or "ようこそ" in plain):
        return "自己紹介"
    if "ここで問題です" in plain or "答えは" in plain or "クイズ" in plain:
        return "復習クイズ"
    if "大切なお知らせ" in plain or "終了することになりました" in plain:
        return "大切なお知らせ"
    if "本当にありがとうございました" in plain or "また次回もお会いしましょう" in plain:
        return "最後のメッセージ"
    if "終了することになりました" in plain or "Kindle" in plain or "お知らせ" in plain:
        return "お知らせ"
    if "思い出してみてください" in plain or "ご紹介しました" in plain:
        return "今日のまとめ"
    if "実写化" in plain and "実写" in plain:
        return "実写と実写化"
    if "上映" in plain:
        return "上映について"
    if "放送" in plain and "配信" in plain:
        return "完成した作品を届ける方法"
    if "監督" in plain and "脚本" in plain:
        return "作品を作っている大切な人"
    if "絵に描いた餅" in plain:
        return "絵に描いた餅"
    if all(term in plain for term in ("絵本", "絵日記", "絵画")):
        return "絵を使った言葉"

    extracted_terms = _extract_topic_terms(plain)
    grouped_heading = _build_group_heading(extracted_terms)
    if grouped_heading:
        return grouped_heading

    keyword_patterns = (
        r"【([^】]{2,16})】",
        r"([一-龯ぁ-んァ-ヶA-Za-z0-9ー]{2,16})という言葉",
        r"([一-龯ぁ-んァ-ヶA-Za-z0-9ー]{2,16}化)",
    )
    keywords: list[str] = []
    for pattern in keyword_patterns:
        for match in re.findall(pattern, plain):
            keyword = _clean_heading_text(match)
            if keyword and keyword not in keywords:
                keywords.append(keyword)
            if len(keywords) == 2:
                return f"{keywords[0]}と{keywords[1]}"
    if len(keywords) == 1:
        return f"{keywords[0]}について"

    repeated_keywords = _extract_repeated_topic_keywords(plain)
    if len(repeated_keywords) >= 2:
        return _clean_heading_text(f"{repeated_keywords[0]}と{repeated_keywords[1]}")
    if len(repeated_keywords) == 1:
        return _clean_heading_text(f"{repeated_keywords[0]}について")

    sentence = plain.split("。", maxsplit=1)[0]
    sentence = re.sub(r"^(まずは|次に|最後に|では、ここで|さて、)", "", sentence).strip()
    sentence = re.sub(r"(です|ます|について).*$", "", sentence).strip()
    return sentence[:18] or "本文"


def _derive_document_title(
    *,
    explicit_title: Optional[str],
    headings: list[str],
    sections: list[tuple[str, str]],
) -> str:
    if explicit_title and explicit_title not in {"本文", "セクション"}:
        return explicit_title

    intro_text = _plain_section_text(sections[0][1]) if sections else ""
    pattern = re.search(
        r"今日はそんな(?P<topic>.+?)を見るときに知っていると役立つ言葉",
        intro_text,
    )
    if pattern:
        topic = pattern.group("topic").strip()
        return _clean_heading_text(f"{topic}を見るときに役立つ言葉")

    for pattern in (
        r"今日は(?P<topic>.+?)をいくつかご紹介します",
        r"今日は(?P<topic>.+?)をご紹介します",
        r"今日はこの(?P<topic>.+?)について(?:ちょっと)?考えてみたい",
        r"今日は(?P<topic>.+?)について(?:考えてみたい|お話しします|話します)",
    ):
        if match := re.search(pattern, intro_text):
            return _clean_heading_text(match.group("topic"))

    all_terms = _extract_topic_terms("\n".join(content for _, content in sections))
    grouped_title = _build_group_heading(all_terms, suffix="日本語表現")
    if grouped_title:
        return grouped_title

    if headings:
        for heading in headings:
            if heading not in {"本文", "イントロダクション"}:
                return heading
        return headings[0]
    return "JP Transcript"


def _extract_topic_terms(text: str) -> list[str]:
    candidates: list[str] = []
    patterns = (
        r"(?:まず(?:一つ目)?|一つ目|二つ目|三つ目|四つ目|五つ目|最後)は[、 ]*([^。\n]{2,24}?)(?:です|といいます)",
        r"([一-龯ぁ-んァ-ヶA-Za-z0-9ー]{2,24})という言葉",
        r"([一-龯ぁ-んァ-ヶA-Za-z0-9ー]{2,24})(?:について|とは)",
        r"【([^】]{2,24})】",
    )
    for pattern in patterns:
        for match in re.findall(pattern, text):
            cleaned = _clean_heading_text(match)
            cleaned = re.sub(r"^(この|その|あの|今日の?)", "", cleaned).strip()
            if _is_useful_topic_term(cleaned) and cleaned not in candidates:
                candidates.append(cleaned)
    return candidates


def _extract_repeated_topic_keywords(text: str) -> list[str]:
    counts: Counter[str] = Counter()
    for match in re.findall(r"[一-龯ァ-ヶーA-Za-z0-9]{2,12}", text):
        cleaned = _clean_heading_text(match)
        if not _is_useful_topic_term(cleaned):
            continue
        if re.fullmatch(r"[A-Za-z0-9]{2,12}", cleaned):
            continue
        counts[cleaned] += 1
    return [keyword for keyword, count in counts.most_common() if count >= 2][:3]


def _build_group_heading(terms: list[str], *, suffix: str = "言葉") -> Optional[str]:
    if not terms:
        return None
    if len(terms) == 1:
        return terms[0]
    if len(terms) == 2:
        return _clean_heading_text(f"{terms[0]}と{terms[1]}")

    leading_chars = [
        term[0]
        for term in terms
        if term and re.fullmatch(r"[一-龯ァ-ヶー]", term[0])
    ]
    if leading_chars:
        character, frequency = Counter(leading_chars).most_common(1)[0]
        if frequency >= 3:
            return _clean_heading_text(f"{character}を使った{suffix}")

    return None


def _is_useful_topic_term(term: str) -> bool:
    return bool(
        term
        and len(term) >= 2
        and term not in GENERIC_HEADING_STOPWORDS
        and not re.fullmatch(r"[ぁ-んー]{2,}", term)
    )


def _run_furigana_stage(
    text: str,
    *,
    job_paths: JobPaths,
    manifest: dict[str, object],
    progress_callback: ProgressCallback = None,
) -> str:
    _mark_stage_running(
        manifest,
        job_paths=job_paths,
        stage_name="furigana",
        message="Deterministic furigana annotation is running.",
    )
    _emit_progress(
        progress_callback,
        stage="furigana",
        status="started",
        message="[3/7] Furigana annotation started.",
        job_id=job_paths.job_id,
    )
    annotated = auto_add_furigana(text)
    report = validate_furigana(annotated)
    job_paths.stage3_output_path.write_text(annotated, encoding="utf-8")
    manifest["stages"]["furigana"] = {
        "status": "completed",
        "output_file": str(job_paths.stage3_output_path),
        "validation": report,
    }
    write_manifest(job_paths.manifest_path, manifest)
    _emit_progress(
        progress_callback,
        stage="furigana",
        status="completed",
        message="[3/7] Furigana annotation completed.",
        job_id=job_paths.job_id,
    )
    return annotated


def _run_refinement_stage(
    text: str,
    *,
    job_paths: JobPaths,
    manifest: dict[str, object],
    progress_callback: ProgressCallback = None,
) -> str:
    _mark_stage_running(
        manifest,
        job_paths=job_paths,
        stage_name="refinement",
        message="Furigana refinement is running.",
    )
    _emit_progress(
        progress_callback,
        stage="refinement",
        status="started",
        message="[4/7] Furigana refinement started.",
        job_id=job_paths.job_id,
    )
    refined = refine_furigana(text)
    job_paths.stage4_output_path.write_text(refined, encoding="utf-8")
    manifest["stages"]["refinement"] = {
        "status": "completed",
        "output_file": str(job_paths.stage4_output_path),
    }
    write_manifest(job_paths.manifest_path, manifest)
    _emit_progress(
        progress_callback,
        stage="refinement",
        status="completed",
        message="[4/7] Furigana refinement completed.",
        job_id=job_paths.job_id,
    )
    return refined


def _run_glossary_stage(
    text: str,
    *,
    job_paths: JobPaths,
    manifest: dict[str, object],
    client: OllamaChatClient,
    progress_callback: ProgressCallback = None,
) -> str:
    prompt = _load_prompt("glossary.md") + (
        "\n\nThis is one section chunk. Number markers locally starting at *1 "
        "inside this chunk only. Return the original body with markers plus a "
        "local glossary appendix. If you cannot find any useful learner items, "
        "return the body unchanged without adding commentary."
    )

    sections = _split_structured_sections(text)
    _mark_stage_running(
        manifest,
        job_paths=job_paths,
        stage_name="glossary",
        message=f"Glossary building running with {len(sections)} section chunk(s).",
    )
    _emit_progress(
        progress_callback,
        stage="glossary",
        status="started",
        message=f"[5/7] Glossary building started ({len(sections)} section chunk(s)).",
        total=len(sections),
        job_id=job_paths.job_id,
    )
    chunk_records: list[dict[str, object]] = []
    merged_bodies: list[str] = []
    merged_entries: list[str] = []
    global_counter = 1

    for index, section in enumerate(sections, start=1):
        chunk = TextChunk(index=index, text=section, start=0, end=len(section))
        output, _, attempts, fallback = _run_chunk_worker(
            chunk,
            prompt=prompt,
            client=client,
            validator=lambda _source, result: {"pass": True},
            stage_name="glossary",
            fallback_output=section,
        )
        body, entries = _parse_glossary_chunk_output(output)
        renumbered_body, renumbered_entries, global_counter = _renumber_glossary_chunk(
            body, entries, start_number=global_counter
        )

        merged_bodies.append(renumbered_body.strip())
        merged_entries.extend(renumbered_entries)
        chunk_path = job_paths.stage5_chunks_dir / f"section-{index:03d}.md"
        chunk_path.write_text(output, encoding="utf-8")
        chunk_records.append(
            {
                "index": index,
                "output_file": str(chunk_path),
                "attempts": attempts,
                "fallback_used": fallback,
                "local_entry_count": len(entries),
            }
        )
        if _should_emit_chunk_progress(index, len(sections), fallback):
            details = []
            if fallback:
                details.append("section kept without glossary rewrite")
            if entries:
                details.append(f"{len(entries)} local item(s)")
            detail_suffix = f" ({'; '.join(details)})" if details else ""
            _emit_progress(
                progress_callback,
                stage="glossary",
                status="progress",
                message=(
                    f"[5/7] Glossary section {index}/{len(sections)} "
                    f"completed{detail_suffix}."
                ),
                completed=index,
                total=len(sections),
                job_id=job_paths.job_id,
            )

    body_text = _repair_paragraph_document(reassemble_chunks(merged_bodies).strip())
    if merged_entries:
        glossary_text = "\n\n".join(merged_entries)
        final = (
            f"{body_text}\n\n---\n\n### 言葉の解説 (Glossary)\n\n{glossary_text}"
        ).strip()
    else:
        final = body_text

    report = validate_glossary(final) if merged_entries else {
        "pass": True,
        "body_markers": [],
        "glossary_entries": [],
        "markers_match_entries": True,
        "sequential_numbering": True,
        "has_separator": False,
        "has_glossary_heading": False,
        "has_meaning": True,
        "has_examples": True,
        "has_comparison": True,
    }

    job_paths.stage5_output_path.write_text(final, encoding="utf-8")
    manifest["stages"]["glossary"] = {
        "status": "completed",
        "output_file": str(job_paths.stage5_output_path),
        "chunks": chunk_records,
        "validation": report,
    }
    write_manifest(job_paths.manifest_path, manifest)
    _emit_progress(
        progress_callback,
        stage="glossary",
        status="completed",
        message="[5/7] Glossary building completed.",
        completed=len(sections),
        total=len(sections),
        job_id=job_paths.job_id,
    )
    return final


def _split_structured_sections(text: str) -> list[str]:
    cleaned = strip_markdown_toc(text).strip()
    matches = list(re.finditer(r"(?m)^##\s+.+$", cleaned))
    if not matches:
        return [cleaned]

    sections: list[str] = []
    for idx, match in enumerate(matches):
        start = match.start()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(cleaned)
        section = cleaned[start:end].strip()
        if len(section) > DEFAULT_CHUNK_SIZE * 2:
            subchunks = chunk_text_with_metadata(
                section,
                max_chars=DEFAULT_CHUNK_SIZE,
                overlap_chars=DEFAULT_OVERLAP_CHARS,
            )
            sections.extend(subchunk.text for subchunk in subchunks)
        else:
            sections.append(section)
    return sections


def _parse_glossary_chunk_output(text: str) -> tuple[str, list[str]]:
    if "\n---" not in text and "---\n" not in text:
        return normalize_text(text), []

    body, glossary = re.split(r"\n---\s*\n", text, maxsplit=1)
    entries: list[str] = []
    current: list[str] = []
    for line in glossary.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("### "):
            continue
        if re.match(r"^\d+\.\s+.+$", stripped):
            if current:
                entries.append("\n".join(current).strip())
            current = [stripped]
        elif current:
            current.append(line.rstrip())
    if current:
        entries.append("\n".join(current).strip())
    return normalize_text(body), entries


def _renumber_glossary_chunk(
    body: str,
    entries: list[str],
    *,
    start_number: int,
) -> tuple[str, list[str], int]:
    if not entries:
        return body, [], start_number

    local_numbers = [int(match) for match in re.findall(r"\*(\d+)", body)]
    unique_local_numbers = []
    for number in local_numbers:
        if number not in unique_local_numbers:
            unique_local_numbers.append(number)

    mapping = {
        local: start_number + index for index, local in enumerate(unique_local_numbers)
    }

    renumbered_body = re.sub(
        r"\*(\d+)",
        lambda match: f"*{mapping[int(match.group(1))]}",
        body,
    )

    renumbered_entries: list[str] = []
    for entry in entries:
        number_match = re.match(r"^(\d+)\.\s+", entry)
        if not number_match:
            continue
        local_number = int(number_match.group(1))
        global_number = mapping.get(local_number)
        if global_number is None:
            continue
        renumbered_entries.append(
            re.sub(r"^\d+\.", f"{global_number}.", entry, count=1)
        )

    return renumbered_body, renumbered_entries, start_number + len(mapping)


def _run_html_stage(
    text: str,
    *,
    job_paths: JobPaths,
    manifest: dict[str, object],
    progress_callback: ProgressCallback = None,
) -> str:
    _mark_stage_running(
        manifest,
        job_paths=job_paths,
        stage_name="html",
        message="HTML conversion is running.",
    )
    _emit_progress(
        progress_callback,
        stage="html",
        status="started",
        message="[6/7] HTML conversion started.",
        job_id=job_paths.job_id,
    )
    html = convert_to_html(text)
    job_paths.stage6_output_path.write_text(html, encoding="utf-8")
    manifest["stages"]["html"] = {
        "status": "completed",
        "output_file": str(job_paths.stage6_output_path),
    }
    write_manifest(job_paths.manifest_path, manifest)
    _emit_progress(
        progress_callback,
        stage="html",
        status="completed",
        message="[6/7] HTML conversion completed.",
        job_id=job_paths.job_id,
    )
    return html


def _run_beautify_stage(
    html: str,
    *,
    structured_markdown: str,
    job_paths: JobPaths,
    manifest: dict[str, object],
    progress_callback: ProgressCallback = None,
) -> pathlib.Path:
    _mark_stage_running(
        manifest,
        job_paths=job_paths,
        stage_name="beautify",
        message="HTML beautification is running.",
    )
    _emit_progress(
        progress_callback,
        stage="beautify",
        status="started",
        message="[7/7] HTML beautification started.",
        job_id=job_paths.job_id,
    )
    beautified = apply_design_template(html)
    job_paths.stage7_output_path.write_text(beautified, encoding="utf-8")

    title_match = re.search(r"(?m)^#\s+(.+)$", structured_markdown)
    if title_match:
        topic_slug = slugify_filename(title_match.group(1))
    else:
        headings = extract_markdown_headings(structured_markdown)
        topic_slug = slugify_filename(headings[0] if headings else "jp-transcript-output")
    output_path = pathlib.Path(save_html_file(beautified, topic_slug=topic_slug))

    manifest["stages"]["beautify"] = {
        "status": "completed",
        "working_file": str(job_paths.stage7_output_path),
        "final_output_file": str(output_path),
    }
    write_manifest(job_paths.manifest_path, manifest)
    _emit_progress(
        progress_callback,
        stage="beautify",
        status="completed",
        message=f"[7/7] HTML beautification completed. Output saved to {output_path.name}.",
        job_id=job_paths.job_id,
    )
    return output_path


def _emit_progress(
    callback: ProgressCallback,
    *,
    stage: str,
    status: str,
    message: str,
    stage_index: Optional[int] = None,
    completed: Optional[int] = None,
    total: Optional[int] = None,
    job_id: Optional[str] = None,
) -> None:
    if callback is None:
        return
    resolved_stage_index = stage_index
    if resolved_stage_index is None and stage in STAGE_METADATA:
        resolved_stage_index = STAGE_METADATA[stage][0]
    callback(
        ProgressUpdate(
            stage=stage,
            status=status,
            message=message,
            stage_index=resolved_stage_index or 0,
            completed=completed,
            total=total,
            job_id=job_id,
        )
    )


def _mark_stage_running(
    manifest: dict[str, object],
    *,
    job_paths: JobPaths,
    stage_name: str,
    message: str,
) -> None:
    stage_record = dict(manifest["stages"].get(stage_name, {}))
    stage_record["status"] = "running"
    stage_record["message"] = message
    manifest["stages"][stage_name] = stage_record
    write_manifest(job_paths.manifest_path, manifest)


def _should_emit_chunk_progress(index: int, total: int, fallback_used: bool) -> bool:
    if fallback_used or index in {1, total}:
        return True
    if total <= 6:
        return True
    if total <= 20:
        return index % 2 == 0
    return index % 5 == 0


def _stage_label(stage_name: str) -> str:
    return STAGE_METADATA.get(stage_name, (0, stage_name.replace("_", " ").title()))[1]


def _build_chunk_prompt(chunk: TextChunk) -> str:
    if chunk.overlap_prefix:
        return (
            "Read-only context from the previous chunk. Use it only to maintain "
            "continuity. Do not copy it into your answer.\n\n"
            f"{chunk.overlap_prefix}\n\n"
            "Primary chunk to process and return:\n\n"
            f"{chunk.text}"
        )
    return chunk.text


def _run_chunk_worker(
    chunk: TextChunk,
    *,
    prompt: str,
    client: OllamaChatClient,
    validator: Callable[[str, str], dict[str, object]],
    stage_name: str,
    fallback_output: Optional[str] = None,
) -> tuple[str, dict[str, object], int, bool]:
    """
    Run one chunk with retries.

    Returns:
        output, validation_report, attempts, fallback_used
    """
    attempts = 0
    last_report: dict[str, object] = {"pass": False}
    last_output = fallback_output or chunk.text

    for _ in range(2):
        attempts += 1
        try:
            candidate = client.chat(prompt, _build_chunk_prompt(chunk))
        except PipelineError:
            candidate = fallback_output or chunk.text
        last_report = validator(chunk.text, candidate)
        last_output = candidate
        if last_report.get("pass", False):
            return candidate, last_report, attempts, False

    if len(chunk.text) > MIN_CHUNK_SIZE * 2 and stage_name in {"optimization", "paragraph"}:
        smaller_chunks = chunk_text_with_metadata(
            chunk.text,
            max_chars=max(MIN_CHUNK_SIZE, len(chunk.text) // 2),
            overlap_chars=0,
        )
        child_outputs = []
        for smaller_chunk in smaller_chunks:
            child_output, _, _, _ = _run_chunk_worker(
                smaller_chunk,
                prompt=prompt,
                client=client,
                validator=validator,
                stage_name=stage_name,
                fallback_output=fallback_output,
            )
            child_outputs.append(child_output)
        combined = reassemble_chunks(child_outputs)
        combined_report = validator(chunk.text, combined)
        if combined_report.get("pass", False):
            return combined, combined_report, attempts, False
        last_output = combined
        last_report = combined_report

    return fallback_output or last_output, last_report, attempts, True
