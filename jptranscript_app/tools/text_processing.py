"""
Core text-processing utilities for jptranscript_app.

This module intentionally keeps large transcript bodies out of ADK session state.
It provides safe file handling, chunk planning, validation helpers, and file save
utilities for the local transcript pipeline.
"""

from __future__ import annotations

import json
import pathlib
import re
import time
import unicodedata
import uuid
from dataclasses import asdict
from dataclasses import dataclass
from html import unescape
from typing import Iterable
from typing import Sequence


APP_DIR = pathlib.Path(__file__).resolve().parent.parent
OUTPUT_DIR = APP_DIR / "Output"
WORK_DIR = APP_DIR / "Work"

JAPANESE_SCRIPT_CHARS = r"\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff々ゝゞー"
ASCII_WORD_CHARS = r"A-Za-z0-9"
JAPANESE_PUNCTUATION = re.escape("、。！？：；（）「」『』【】〔〕［］｛｝〈〉《》・，．…〜")

RAW_TIMESTAMP_LINE_PATTERN = re.compile(
    r"^\s*(?:\[(?P<bracketed>\d{1,2}:\d{2}(?::\d{2})?)\]|(?P<plain>\d{1,2}:\d{2}(?::\d{2})?))\s*$"
)
PROTECTED_TIMESTAMP_PATTERN = re.compile(
    r"^\s*\[\[TIMESTAMP:(?P<value>\d{1,2}:\d{2}(?::\d{2})?)\]\]\s*$"
)

DEFAULT_CHUNK_SIZE = 1400
DEFAULT_OVERLAP_CHARS = 120
MIN_CHUNK_SIZE = 350


class PipelineError(RuntimeError):
    """Raised when the local transcript pipeline cannot complete safely."""


class InputResolutionError(PipelineError):
    """Raised when user input cannot be resolved into transcript text."""


@dataclass(frozen=True)
class TextChunk:
    """A chunk of text with enough metadata for chunk-local retries."""

    index: int
    text: str
    start: int
    end: int
    overlap_prefix: str = ""

    @property
    def chunk_id(self) -> str:
        return f"chunk-{self.index:03d}"

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class JobPaths:
    """Filesystem layout for one pipeline execution."""

    job_id: str
    job_dir: pathlib.Path
    manifest_path: pathlib.Path
    raw_input_path: pathlib.Path
    stage1_chunks_dir: pathlib.Path
    stage1_output_path: pathlib.Path
    stage2_chunks_dir: pathlib.Path
    stage2_output_path: pathlib.Path
    stage3_output_path: pathlib.Path
    stage4_output_path: pathlib.Path
    stage5_chunks_dir: pathlib.Path
    stage5_output_path: pathlib.Path
    stage6_output_path: pathlib.Path
    stage7_output_path: pathlib.Path


def normalize_text(text: str) -> str:
    """Normalize line endings and strip BOM-like noise without changing content."""
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    normalized = normalized.lstrip("\ufeff")
    return normalized.strip()


def collapse_meaningless_japanese_spacing(text: str) -> str:
    """
    Remove OCR- or subtitle-like spaces that split Japanese words into characters.

    This runs as a deterministic safety net after the optimization model step.
    It only collapses whitespace where Japanese text, punctuation, or mixed
    Japanese/ASCII tokens are unnaturally separated. Pure ASCII spacing such as
    ``JLPT N3`` is preserved.
    """
    collapsed_lines: list[str] = []
    for raw_line in normalize_text(text).splitlines():
        stripped = raw_line.strip()
        if not stripped:
            collapsed_lines.append("")
            continue
        if RAW_TIMESTAMP_LINE_PATTERN.fullmatch(stripped) or PROTECTED_TIMESTAMP_PATTERN.fullmatch(
            stripped
        ):
            collapsed_lines.append(stripped)
            continue
        collapsed_lines.append(_collapse_spacing_in_line(raw_line))
    return "\n".join(collapsed_lines)


def _collapse_spacing_in_line(line: str) -> str:
    leading = re.match(r"^\s*", line).group(0)
    trailing = re.search(r"\s*$", line).group(0)
    body = line[len(leading) : len(line) - len(trailing) if trailing else len(line)]
    body = body.replace("\u3000", " ")

    patterns = (
        rf"(?<=[{JAPANESE_SCRIPT_CHARS}])\s+(?=[{JAPANESE_SCRIPT_CHARS}])",
        rf"(?<=[{JAPANESE_SCRIPT_CHARS}])\s+(?=[{JAPANESE_PUNCTUATION}])",
        rf"(?<=[{JAPANESE_PUNCTUATION}])\s+(?=[{JAPANESE_SCRIPT_CHARS}])",
        rf"(?<=[{ASCII_WORD_CHARS}])\s+(?=[{JAPANESE_SCRIPT_CHARS}])",
        rf"(?<=[{JAPANESE_SCRIPT_CHARS}])\s+(?=[{ASCII_WORD_CHARS}])",
    )

    previous = None
    while body != previous:
        previous = body
        for pattern in patterns:
            body = re.sub(pattern, "", body)

    body = re.sub(r" {2,}", " ", body)
    return f"{leading}{body.strip()}{trailing}"


def count_meaningless_japanese_spacing(text: str) -> int:
    """Return the number of suspicious Japanese character-gap runs in ``text``."""
    normalized = normalize_text(text)
    patterns = (
        rf"(?<=[{JAPANESE_SCRIPT_CHARS}])\s+(?=[{JAPANESE_SCRIPT_CHARS}])",
        rf"(?<=[{JAPANESE_SCRIPT_CHARS}])\s+(?=[{JAPANESE_PUNCTUATION}])",
        rf"(?<=[{JAPANESE_PUNCTUATION}])\s+(?=[{JAPANESE_SCRIPT_CHARS}])",
        rf"(?<=[{ASCII_WORD_CHARS}])\s+(?=[{JAPANESE_SCRIPT_CHARS}])",
        rf"(?<=[{JAPANESE_SCRIPT_CHARS}])\s+(?=[{ASCII_WORD_CHARS}])",
    )
    return sum(len(re.findall(pattern, normalized)) for pattern in patterns)


def protect_timestamps(text: str) -> str:
    """Wrap standalone timestamps in stable markers for model-facing stages."""
    protected_lines = []
    for line in normalize_text(text).splitlines():
        stripped = line.strip()
        if match := RAW_TIMESTAMP_LINE_PATTERN.fullmatch(stripped):
            value = match.group("bracketed") or match.group("plain")
            protected_lines.append(f"[[TIMESTAMP:{value}]]")
        else:
            protected_lines.append(line)
    return "\n".join(protected_lines)


def restore_timestamps(text: str) -> str:
    """Restore protected timestamp markers back to display form."""
    restored_lines = []
    for line in normalize_text(text).splitlines():
        stripped = line.strip()
        if match := PROTECTED_TIMESTAMP_PATTERN.fullmatch(stripped):
            restored_lines.append(match.group("value"))
        else:
            restored_lines.append(line)
    return "\n".join(restored_lines)


def extract_timestamps(text: str) -> list[str]:
    """Return standalone timestamps in document order."""
    values: list[str] = []
    for line in normalize_text(text).splitlines():
        stripped = line.strip()
        if match := PROTECTED_TIMESTAMP_PATTERN.fullmatch(stripped):
            values.append(match.group("value"))
            continue
        if match := RAW_TIMESTAMP_LINE_PATTERN.fullmatch(stripped):
            values.append(match.group("bracketed") or match.group("plain"))
    return values


def make_job_paths() -> JobPaths:
    """Create a unique work directory for a pipeline job."""
    WORK_DIR.mkdir(exist_ok=True)
    job_id = f"{time.strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:8]}"
    job_dir = WORK_DIR / job_id
    job_dir.mkdir(parents=True, exist_ok=False)

    stage1_chunks_dir = job_dir / "stage1_chunks"
    stage2_chunks_dir = job_dir / "stage2_chunks"
    stage5_chunks_dir = job_dir / "stage5_chunks"
    for chunk_dir in (stage1_chunks_dir, stage2_chunks_dir, stage5_chunks_dir):
        chunk_dir.mkdir(parents=True, exist_ok=True)

    return JobPaths(
        job_id=job_id,
        job_dir=job_dir,
        manifest_path=job_dir / "manifest.json",
        raw_input_path=job_dir / "stage0_raw.txt",
        stage1_chunks_dir=stage1_chunks_dir,
        stage1_output_path=job_dir / "stage1_optimized.txt",
        stage2_chunks_dir=stage2_chunks_dir,
        stage2_output_path=job_dir / "stage2_structured.md",
        stage3_output_path=job_dir / "stage3_furigana.txt",
        stage4_output_path=job_dir / "stage4_refined.txt",
        stage5_chunks_dir=stage5_chunks_dir,
        stage5_output_path=job_dir / "stage5_glossary.md",
        stage6_output_path=job_dir / "stage6_output.html",
        stage7_output_path=job_dir / "stage7_output.html",
    )


def initialize_manifest(
    job_paths: JobPaths,
    *,
    source_type: str,
    source_label: str,
) -> dict[str, object]:
    """Create the on-disk manifest that records stage outputs and retries."""
    manifest: dict[str, object] = {
        "job_id": job_paths.job_id,
        "source_type": source_type,
        "source_label": source_label,
        "created_at_epoch": time.time(),
        "stages": {
            "optimization": {"status": "pending", "chunks": []},
            "paragraph": {"status": "pending", "chunks": []},
            "furigana": {"status": "pending"},
            "refinement": {"status": "pending"},
            "glossary": {"status": "pending", "chunks": []},
            "html": {"status": "pending"},
            "beautify": {"status": "pending"},
        },
    }
    write_manifest(job_paths.manifest_path, manifest)
    return manifest


def write_manifest(path: pathlib.Path, manifest: dict[str, object]) -> None:
    """Persist the manifest with stable formatting for debugging."""
    path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def read_transcript_file(file_path: str) -> str:
    """
    Read a transcript file safely.

    Relative paths are resolved against ``jptranscript_app/`` and may not escape
    that directory. Absolute paths are allowed if explicitly provided.
    """
    candidate = pathlib.Path(file_path).expanduser()
    if candidate.is_absolute():
        resolved = candidate.resolve()
    else:
        resolved = (APP_DIR / candidate).resolve()
        if APP_DIR not in resolved.parents and resolved != APP_DIR:
            raise InputResolutionError(
                f"Relative transcript paths must stay inside {APP_DIR}."
            )

    if resolved.suffix.lower() != ".txt":
        raise InputResolutionError(
            f"Transcript file must end with .txt, got: {resolved.name}"
        )
    if not resolved.exists() or not resolved.is_file():
        raise InputResolutionError(f"Transcript file not found: {resolved}")

    return normalize_text(resolved.read_text(encoding="utf-8"))


def detect_input_text(user_input: str) -> tuple[str, str, str]:
    """
    Resolve the user's message into transcript text.

    Returns:
        tuple[text, source_type, source_label]
    """
    stripped = user_input.strip()
    if not stripped:
        raise InputResolutionError(
            "Please provide Japanese transcript text or a .txt file path."
        )

    looks_like_path = "\n" not in stripped and stripped.lower().endswith(".txt")
    if looks_like_path:
        return read_transcript_file(stripped), "file", stripped

    return normalize_text(stripped), "text", "pasted transcript"


def estimate_token_count(text: str) -> int:
    """
    Cheap token heuristic for chunk sizing on mixed Japanese/ASCII text.

    This intentionally overestimates Japanese-heavy content to keep chunks safe
    for local models with limited practical context.
    """
    ascii_runs = re.findall(r"[A-Za-z0-9_]+", text)
    ascii_tokens = len(ascii_runs)
    japanese_chars = sum(1 for ch in text if _is_japanese_script_char(ch))
    other_chars = max(0, len(text) - japanese_chars - sum(len(run) for run in ascii_runs))
    return ascii_tokens + japanese_chars + (other_chars // 2)


def _is_japanese_script_char(ch: str) -> bool:
    return (
        "\u3040" <= ch <= "\u30ff"
        or "\u3400" <= ch <= "\u4dbf"
        or "\u4e00" <= ch <= "\u9fff"
        or ch in "々ゝゞー"
    )


def chunk_text(text: str, max_chars: int = DEFAULT_CHUNK_SIZE) -> list[str]:
    """Compatibility helper that returns only chunk text."""
    return [chunk.text for chunk in chunk_text_with_metadata(text, max_chars=max_chars)]


def chunk_text_with_metadata(
    text: str,
    *,
    max_chars: int = DEFAULT_CHUNK_SIZE,
    overlap_chars: int = DEFAULT_OVERLAP_CHARS,
) -> list[TextChunk]:
    """
    Split text into safe processing chunks.

    The chunker prefers headings, paragraph breaks, speaker turns, and sentence
    boundaries. Overlap is recorded separately and can be passed as read-only
    context to a chunk worker.
    """
    text = normalize_text(text)
    if not text:
        return []
    if len(text) <= max_chars:
        return [TextChunk(index=1, text=text, start=0, end=len(text))]

    chunks: list[TextChunk] = []
    cursor = 0
    index = 1

    while cursor < len(text):
        remaining = len(text) - cursor
        if remaining <= max_chars:
            overlap_prefix = text[max(0, cursor - overlap_chars) : cursor]
            chunks.append(
                TextChunk(
                    index=index,
                    text=text[cursor:],
                    start=cursor,
                    end=len(text),
                    overlap_prefix=overlap_prefix,
                )
            )
            break

        window_end = min(len(text), cursor + max_chars)
        split_at = _find_split_point(text, cursor, window_end, max_chars=max_chars)
        if split_at <= cursor:
            split_at = window_end

        overlap_prefix = text[max(0, cursor - overlap_chars) : cursor]
        chunks.append(
            TextChunk(
                index=index,
                text=text[cursor:split_at].rstrip(),
                start=cursor,
                end=split_at,
                overlap_prefix=overlap_prefix,
            )
        )

        cursor = split_at
        while cursor < len(text) and text[cursor] == "\n":
            cursor += 1
        index += 1

    return chunks


def _find_split_point(
    text: str,
    start: int,
    window_end: int,
    *,
    max_chars: int,
) -> int:
    window = text[start:window_end]
    minimum = max(MIN_CHUNK_SIZE, int(max_chars * 0.45))

    patterns = (
        "\n## ",
        "\n### ",
        "\n\n",
        "\n",
        "。",
        "！",
        "？",
    )
    best = -1
    for pattern in patterns:
        position = window.rfind(pattern)
        if position >= minimum:
            best = start + position + len(pattern)
            break

    if best != -1:
        return best

    speaker_matches = list(
        re.finditer(r"\n(?:\*\*)?[^\n]{1,24}(?:\*\*)?[：:]", window)
    )
    if speaker_matches:
        last = speaker_matches[-1]
        if last.start() >= minimum:
            return start + last.start() + 1

    return window_end


def reassemble_chunks(chunks: Iterable[str]) -> str:
    """Join chunk outputs while preserving blank-line separation."""
    cleaned = [chunk.strip() for chunk in chunks if chunk and chunk.strip()]
    return "\n\n".join(cleaned)


def strip_markdown_toc(markdown_text: str) -> str:
    """Remove a markdown TOC block so it can be rebuilt globally."""
    lines = markdown_text.splitlines()
    output: list[str] = []
    i = 0
    while i < len(lines):
        stripped = lines[i].strip()
        if stripped == "**目次**":
            i += 1
            while i < len(lines):
                current = lines[i].strip()
                if not current:
                    i += 1
                    continue
                if re.match(r"^[-*]\s+", current):
                    i += 1
                    continue
                break
            continue
        output.append(lines[i])
        i += 1
    return "\n".join(output).strip()


def extract_markdown_headings(markdown_text: str, level: int = 2) -> list[str]:
    """Return markdown heading text in document order."""
    pattern = re.compile(rf"^{'#' * level}\s+(.+)$", re.MULTILINE)
    headings: list[str] = []
    for match in pattern.finditer(markdown_text):
        heading = re.sub(r"（[ぁ-ん]+）", "", match.group(1)).strip()
        if heading:
            headings.append(unescape(heading))
    return headings


def build_markdown_toc(headings: Sequence[str]) -> str:
    """Create a simple markdown TOC block from H2 headings."""
    if not headings:
        return ""
    body = "\n".join(f"- {heading}" for heading in headings)
    return f"**目次**\n{body}\n"


def validate_optimization(input_text: str, output_text: str) -> dict[str, object]:
    """Validate stage 1 output conservatively."""
    results: dict[str, object] = {}
    normalized_input = restore_timestamps(normalize_text(input_text))
    normalized_output = restore_timestamps(normalize_text(output_text))
    comparison_input = collapse_meaningless_japanese_spacing(normalized_input)
    comparison_output = collapse_meaningless_japanese_spacing(normalized_output)

    ratio = (
        len(comparison_output) / len(comparison_input)
        if comparison_input
        else 0.0
    )
    input_speakers = set(
        re.findall(r"(?:\*\*)?([^\n\*]{1,24})(?:\*\*)?[：:]", normalized_input)
    )
    output_speakers = set(
        re.findall(r"(?:\*\*)?([^\n\*]{1,24})(?:\*\*)?[：:]", normalized_output)
    )
    marker_leak = bool(re.search(r"\[Processing chunk \d+ of \d+\]", normalized_output))
    input_timestamps = extract_timestamps(normalized_input)
    output_timestamps = extract_timestamps(normalized_output)
    input_spacing_gaps = count_meaningless_japanese_spacing(normalized_input)
    output_spacing_gaps = count_meaningless_japanese_spacing(normalized_output)

    results["char_ratio"] = round(ratio, 3)
    results["char_ratio_pass"] = 0.65 <= ratio <= 1.10
    results["speakers_preserved"] = input_speakers.issubset(output_speakers)
    results["input_speaker_count"] = len(input_speakers)
    results["output_speaker_count"] = len(output_speakers)
    results["non_empty"] = bool(normalized_output)
    results["chunk_marker_leak"] = marker_leak
    results["input_timestamps"] = input_timestamps
    results["output_timestamps"] = output_timestamps
    results["timestamps_preserved"] = (
        input_timestamps == output_timestamps if input_timestamps else True
    )
    results["input_spacing_gaps"] = input_spacing_gaps
    results["output_spacing_gaps"] = output_spacing_gaps
    results["spacing_improved"] = (
        output_spacing_gaps <= max(1, input_spacing_gaps // 8)
        if input_spacing_gaps
        else True
    )
    results["pass"] = all(
        (
            results["char_ratio_pass"],
            results["speakers_preserved"],
            results["non_empty"],
            not marker_leak,
            results["timestamps_preserved"],
            results["spacing_improved"],
        )
    )
    return results


def validate_paragraph(input_text: str, output_text: str) -> dict[str, object]:
    """Validate stage 2 output."""
    results: dict[str, object] = {}
    normalized_input = restore_timestamps(normalize_text(input_text))
    normalized_output = restore_timestamps(normalize_text(output_text))

    headings = extract_markdown_headings(normalized_output, level=2)
    toc_present = normalized_output.startswith("**目次**")
    clean_input = re.sub(r"[#*\-\n\s]", "", normalized_input)
    clean_output = re.sub(r"[#*\-\n\s]", "", normalized_output)
    ratio = len(clean_output) / len(clean_input) if clean_input else 0.0
    input_timestamps = extract_timestamps(normalized_input)
    output_timestamps = extract_timestamps(normalized_output)

    results["heading_count"] = len(headings)
    results["has_headings"] = bool(headings)
    results["has_toc"] = toc_present
    results["content_ratio"] = round(ratio, 3)
    results["content_preserved"] = ratio >= 0.92
    results["input_timestamps"] = input_timestamps
    results["output_timestamps"] = output_timestamps
    results["timestamps_preserved"] = (
        input_timestamps == output_timestamps if input_timestamps else True
    )
    results["pass"] = all(
        (
            results["has_headings"],
            results["has_toc"],
            results["content_preserved"],
            results["timestamps_preserved"],
        )
    )
    return results


def validate_glossary(text: str) -> dict[str, object]:
    """Validate stage 5 output strictly."""
    results: dict[str, object] = {}
    if "\n---" not in text and "---\n" not in text:
        return {
            "body_markers": [],
            "glossary_entries": [],
            "markers_match_entries": False,
            "sequential_numbering": False,
            "has_separator": False,
            "has_glossary_heading": False,
            "has_meaning": False,
            "has_examples": False,
            "has_comparison": False,
            "pass": False,
        }

    body, glossary = re.split(r"\n---\s*\n", text, maxsplit=1)
    body_markers = [int(value) for value in re.findall(r"\*(\d+)", body)]
    entry_blocks = [
        match.group(0).strip()
        for match in re.finditer(
            r"(?ms)^\s*(\d+)\.\s+.+?(?=^\s*\d+\.\s+|\Z)",
            glossary,
        )
    ]
    entry_numbers = [
        int(match.group(1))
        for match in re.finditer(r"(?m)^\s*(\d+)\.\s+.+$", glossary)
    ]

    expected_sequence = list(range(1, len(entry_numbers) + 1))
    results["body_markers"] = body_markers
    results["glossary_entries"] = entry_numbers
    results["markers_match_entries"] = body_markers == entry_numbers
    results["sequential_numbering"] = entry_numbers == expected_sequence
    results["has_separator"] = True
    results["has_glossary_heading"] = "言葉の解説" in glossary

    has_meaning = bool(entry_blocks)
    has_examples = bool(entry_blocks)
    has_comparison = bool(entry_blocks)
    for block in entry_blocks:
        has_meaning = has_meaning and ("意味" in block)
        has_examples = has_examples and ("例文" in block)
        has_comparison = has_comparison and ("比較" in block)

    results["has_meaning"] = has_meaning
    results["has_examples"] = has_examples
    results["has_comparison"] = has_comparison
    results["pass"] = all(
        (
            results["markers_match_entries"],
            results["sequential_numbering"],
            results["has_glossary_heading"],
            results["has_meaning"],
            results["has_examples"],
            results["has_comparison"],
        )
    )
    return results


def slugify_filename(text: str) -> str:
    """Create a readable, filesystem-safe slug while preserving Japanese text."""
    normalized = collapse_meaningless_japanese_spacing(
        unicodedata.normalize("NFKC", text).strip()
    )
    normalized = re.sub(r"（[ぁ-ん]+）", "", normalized)
    normalized = normalized.replace("/", " ")
    normalized = re.sub(r'[<>:"/\\|?*]+', "", normalized)
    normalized = re.sub(r"\s+", "-", normalized)
    return normalized or "jp-transcript-output"


def save_html_file(html_content: str, topic_slug: str = "") -> str:
    """Save the final HTML file to jptranscript_app/Output without overwriting."""
    OUTPUT_DIR.mkdir(exist_ok=True)
    title_match = re.search(r"<title>(.*?)</title>", html_content, re.DOTALL)
    if not topic_slug and title_match:
        topic_slug = slugify_filename(title_match.group(1))
    topic_slug = slugify_filename(topic_slug or "jp-transcript-output")

    candidate = OUTPUT_DIR / f"{topic_slug}.html"
    counter = 1
    while candidate.exists():
        candidate = OUTPUT_DIR / f"{topic_slug}-{counter}.html"
        counter += 1

    candidate.write_text(html_content, encoding="utf-8")
    return str(candidate.resolve())
