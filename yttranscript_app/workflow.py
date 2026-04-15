"""Local YouTube transcript workflow runner."""

from __future__ import annotations

import json
import shutil
from dataclasses import asdict, dataclass
from pathlib import Path
import re
from typing import Callable, Optional

from .tools.html_renderer import render_base_html
from .tools.job_state import APP_DIR
from .tools.job_state import JobPaths
from .tools.job_state import initialize_manifest
from .tools.job_state import make_job_paths
from .tools.job_state import reserve_output_path
from .tools.job_state import write_manifest
from .tools.job_state import write_qa_summary
from .tools.ollama_client import OllamaChatClient
from .tools.ollama_client import OllamaError
from .tools.shadowing_html import OptimizationError
from .tools.shadowing_html import optimize_shadowing_html
from .tools.shadowing_html import parse_input_html
from .tools.transcript_structure import StructureError
from .tools.transcript_structure import StructuredDocument
from .tools.transcript_structure import render_structured_markdown
from .tools.transcript_structure import structure_transcript
from .tools.validate_shadowing_html import ShadowingHtmlValidationReport
from .tools.validate_shadowing_html import validate_shadowing_html_content
from .tools.validate_transcript_integrity import TranscriptIntegrityReport
from .tools.validate_transcript_integrity import validate_transcript_integrity
from .tools.youtube_transcript import TranscriptBuildResult
from .tools.youtube_transcript import TranscriptError
from .tools.youtube_transcript import canonicalize_youtube_url
from .tools.youtube_transcript import extract_youtube_video_id
from .tools.youtube_transcript import generate_transcript


TOTAL_STAGES = 4
REFERENCE_HTML_PATH = APP_DIR / "fixtures" / "html_reference" / "ai-agent-design-patterns.html"
YOUTUBE_URL_RE = re.compile(r"https?://[^\s<>()]+", re.IGNORECASE)
LANG_HINT_RE = re.compile(
    r"(?:lang|language|captions?)\s*[:=]\s*([A-Za-z]{2,3}(?:-[A-Za-z]{2,4})?)",
    re.IGNORECASE,
)


class PipelineError(RuntimeError):
    """Raised when the local transcript workflow cannot complete safely."""


@dataclass(frozen=True)
class PipelineResult:
    job_id: str
    output_path: Path
    manifest_path: Path
    qa_summary_path: Path
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


@dataclass(frozen=True)
class YouTubeRequest:
    raw_input: str
    raw_url: str
    canonical_url: str
    video_id: str
    language_hint: str | None


ProgressCallback = Optional[Callable[[ProgressUpdate], None]]


def run_transcript_pipeline(
    user_input: str,
    *,
    client: Optional[OllamaChatClient] = None,
    progress_callback: ProgressCallback = None,
) -> PipelineResult:
    """Run the full local YouTube transcript pipeline and return the saved HTML path."""
    request = _parse_user_request(user_input)
    model_client = client or OllamaChatClient()
    job_paths = make_job_paths()
    manifest = initialize_manifest(
        job_paths,
        source_url=request.canonical_url,
        video_id=request.video_id,
        language_hint=request.language_hint,
    )
    warnings: list[str] = []
    reference_html = _load_reference_html()

    request_record = {
        "raw_input": request.raw_input,
        "raw_url": request.raw_url,
        "canonical_url": request.canonical_url,
        "video_id": request.video_id,
        "language_hint": request.language_hint,
        "ollama_model": model_client.model,
    }
    job_paths.stage0_request_path.write_text(
        json.dumps(request_record, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    manifest["last_run_status"] = "running"
    write_manifest(job_paths.manifest_path, manifest)
    _emit_progress(
        progress_callback,
        stage="pipeline",
        status="started",
        message=f"Started YouTube transcript build. Job ID: {job_paths.job_id}.",
        job_id=job_paths.job_id,
    )

    current_stage = "pipeline"
    transcript_result: TranscriptBuildResult | None = None
    integrity_report: TranscriptIntegrityReport | None = None
    html_validation: ShadowingHtmlValidationReport | None = None

    try:
        current_stage = "transcript"
        transcript_result = _run_transcript_stage(
            request,
            job_paths=job_paths,
            manifest=manifest,
            progress_callback=progress_callback,
        )
        if transcript_result.source_label.startswith("whisper ASR"):
            warnings.append(
                "Transcript completeness required ASR fallback because subtitle coverage was insufficient."
            )

        current_stage = "structure"
        document, integrity_report = _run_structure_stage(
            transcript_result,
            job_paths=job_paths,
            manifest=manifest,
            client=model_client,
            progress_callback=progress_callback,
        )

        current_stage = "base_html"
        render_title = _run_base_html_stage(
            document,
            job_paths=job_paths,
            manifest=manifest,
            progress_callback=progress_callback,
        )

        current_stage = "shadowing_html"
        output_path, html_validation = _run_shadowing_stage(
            request,
            render_title=render_title,
            job_paths=job_paths,
            manifest=manifest,
            progress_callback=progress_callback,
            reference_html=reference_html,
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
            stage_index=_stage_index(current_stage),
            job_id=job_paths.job_id,
        )
        raise

    qa_summary = {
        "job_id": job_paths.job_id,
        "source_url": request.canonical_url,
        "output_path": str(output_path),
        "warnings": warnings,
        "transcript": {
            "language": transcript_result.language if transcript_result else "unknown",
            "source_label": transcript_result.source_label if transcript_result else "",
            "report": transcript_result.report if transcript_result else {},
            "cue_count": len(transcript_result.segments) if transcript_result else 0,
        },
        "structure": {
            "section_count": integrity_report.section_count if integrity_report else 0,
            "found_summary": integrity_report.found_summary if integrity_report else False,
        },
        "shadowing_html": {
            "cue_count": html_validation.cue_count if html_validation else 0,
            "ruby_count": html_validation.ruby_count if html_validation else 0,
        },
    }
    write_qa_summary(job_paths.qa_summary_path, qa_summary)

    manifest["final_output_path"] = str(output_path)
    manifest["qa_summary_path"] = str(job_paths.qa_summary_path)
    manifest["last_run_status"] = "completed"
    if warnings:
        manifest["warnings"] = warnings
    write_manifest(job_paths.manifest_path, manifest)
    _emit_progress(
        progress_callback,
        stage="shadowing_html",
        status="completed",
        message="[4/4] Shadowing HTML completed.",
        stage_index=4,
        job_id=job_paths.job_id,
    )

    return PipelineResult(
        job_id=job_paths.job_id,
        output_path=output_path,
        manifest_path=job_paths.manifest_path,
        qa_summary_path=job_paths.qa_summary_path,
        source_type="youtube",
        source_label=request.canonical_url,
        warnings=tuple(warnings),
    )


def _parse_user_request(user_input: str) -> YouTubeRequest:
    match = YOUTUBE_URL_RE.search(user_input)
    if not match:
        raise PipelineError("Paste a YouTube video URL to build the shadowing materials.")

    raw_url = match.group(0).rstrip(".,)")
    try:
        canonical_url = canonicalize_youtube_url(raw_url)
        video_id = extract_youtube_video_id(raw_url)
    except TranscriptError as exc:
        raise PipelineError(str(exc)) from exc

    lang_match = LANG_HINT_RE.search(user_input)
    language_hint = lang_match.group(1) if lang_match else None
    return YouTubeRequest(
        raw_input=user_input.strip(),
        raw_url=raw_url,
        canonical_url=canonical_url,
        video_id=video_id,
        language_hint=language_hint,
    )


def _load_reference_html() -> str:
    if REFERENCE_HTML_PATH.exists():
        return REFERENCE_HTML_PATH.read_text(encoding="utf-8")
    fallback_path = APP_DIR / "Output" / "ai-agent-design-patterns.html"
    if fallback_path.exists():
        return fallback_path.read_text(encoding="utf-8")
    return ""


def _run_transcript_stage(
    request: YouTubeRequest,
    *,
    job_paths: JobPaths,
    manifest: dict[str, object],
    progress_callback: ProgressCallback = None,
) -> TranscriptBuildResult:
    _mark_stage_running(
        manifest,
        job_paths=job_paths,
        stage_name="transcript",
        message="Transcript acquisition started.",
    )
    _emit_progress(
        progress_callback,
        stage="transcript",
        status="started",
        message="[1/4] Transcript acquisition started.",
        stage_index=1,
        job_id=job_paths.job_id,
    )
    try:
        result = generate_transcript(
            request.canonical_url,
            output_path=job_paths.stage1_transcript_path,
            lang=request.language_hint,
        )
    except TranscriptError as exc:
        raise PipelineError(str(exc)) from exc

    manifest["stages"]["transcript"] = {
        "status": "completed",
        "output_file": str(job_paths.stage1_transcript_path),
        "language": result.language,
        "source_label": result.source_label,
        "cue_count": len(result.segments),
        "coverage_report": result.report,
    }
    write_manifest(job_paths.manifest_path, manifest)
    _emit_progress(
        progress_callback,
        stage="transcript",
        status="completed",
        message="[1/4] Transcript acquisition completed.",
        stage_index=1,
        completed=len(result.segments),
        total=len(result.segments),
        job_id=job_paths.job_id,
    )
    return result


def _run_structure_stage(
    transcript_result: TranscriptBuildResult,
    *,
    job_paths: JobPaths,
    manifest: dict[str, object],
    client: OllamaChatClient,
    progress_callback: ProgressCallback = None,
) -> tuple[StructuredDocument, TranscriptIntegrityReport]:
    _mark_stage_running(
        manifest,
        job_paths=job_paths,
        stage_name="structure",
        message="Gemma transcript structuring started.",
    )
    _emit_progress(
        progress_callback,
        stage="structure",
        status="started",
        message="[2/4] Transcript structuring started.",
        stage_index=2,
        job_id=job_paths.job_id,
    )
    try:
        document = structure_transcript(transcript_result.content, client=client)
    except (StructureError, OllamaError) as exc:
        raise PipelineError(str(exc)) from exc

    structure_record = {
        "metadata": asdict(document.metadata),
        "sections": [
            {
                "title": section.title,
                "start_cue_index": section.cues[0].index,
                "end_cue_index": section.cues[-1].index,
                "cue_count": len(section.cues),
            }
            for section in document.sections
        ],
        "takeaways": list(document.takeaways),
        "ollama_model": client.model,
    }
    job_paths.stage2_structure_json_path.write_text(
        json.dumps(structure_record, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    structured_markdown = render_structured_markdown(document)
    job_paths.stage2_structured_md_path.write_text(structured_markdown, encoding="utf-8")
    integrity_report = validate_transcript_integrity(
        transcript_result.content,
        structured_markdown,
    )
    if not integrity_report.passed:
        raise PipelineError("; ".join(integrity_report.errors))

    manifest["stages"]["structure"] = {
        "status": "completed",
        "output_files": [
            str(job_paths.stage2_structure_json_path),
            str(job_paths.stage2_structured_md_path),
        ],
        "section_count": len(document.sections),
        "takeaway_count": len(document.takeaways),
        "validation": {
            "passed": integrity_report.passed,
            "section_count": integrity_report.section_count,
            "found_summary": integrity_report.found_summary,
        },
    }
    write_manifest(job_paths.manifest_path, manifest)
    _emit_progress(
        progress_callback,
        stage="structure",
        status="completed",
        message="[2/4] Transcript structuring completed.",
        stage_index=2,
        completed=len(document.sections),
        total=len(document.sections),
        job_id=job_paths.job_id,
    )
    return document, integrity_report


def _run_base_html_stage(
    document: StructuredDocument,
    *,
    job_paths: JobPaths,
    manifest: dict[str, object],
    progress_callback: ProgressCallback = None,
) -> str:
    _mark_stage_running(
        manifest,
        job_paths=job_paths,
        stage_name="base_html",
        message="Deterministic base HTML rendering started.",
    )
    _emit_progress(
        progress_callback,
        stage="base_html",
        status="started",
        message="[3/4] Base HTML rendering started.",
        stage_index=3,
        job_id=job_paths.job_id,
    )

    render = render_base_html(
        title=document.metadata.title,
        source_url=document.metadata.source_url,
        document=document,
    )
    job_paths.stage3_base_html_path.write_text(render.html_content, encoding="utf-8")
    parsed_title, parsed_cues, parsed_takeaways = parse_input_html(job_paths.stage3_base_html_path)
    if len(parsed_cues) != sum(len(section.cues) for section in document.sections):
        raise PipelineError("Base HTML cue count did not match the structured transcript.")

    manifest["stages"]["base_html"] = {
        "status": "completed",
        "output_file": str(job_paths.stage3_base_html_path),
        "title": parsed_title,
        "cue_count": len(parsed_cues),
        "takeaway_count": len(parsed_takeaways),
    }
    write_manifest(job_paths.manifest_path, manifest)
    _emit_progress(
        progress_callback,
        stage="base_html",
        status="completed",
        message="[3/4] Base HTML rendering completed.",
        stage_index=3,
        completed=len(parsed_cues),
        total=len(parsed_cues),
        job_id=job_paths.job_id,
    )
    return render.title


def _run_shadowing_stage(
    request: YouTubeRequest,
    *,
    render_title: str,
    job_paths: JobPaths,
    manifest: dict[str, object],
    progress_callback: ProgressCallback = None,
    reference_html: str = "",
) -> tuple[Path, ShadowingHtmlValidationReport]:
    _mark_stage_running(
        manifest,
        job_paths=job_paths,
        stage_name="shadowing_html",
        message="Interactive shadowing HTML build started.",
    )
    _emit_progress(
        progress_callback,
        stage="shadowing_html",
        status="started",
        message="[4/4] Shadowing HTML build started.",
        stage_index=4,
        job_id=job_paths.job_id,
    )

    try:
        build_result = optimize_shadowing_html(
            job_paths.stage3_base_html_path,
            request.canonical_url,
            output_path=job_paths.stage4_shadowing_html_path,
            title=render_title,
        )
    except OptimizationError as exc:
        raise PipelineError(str(exc)) from exc

    validation = validate_shadowing_html_content(
        build_result.html_content,
        youtube_url=request.canonical_url,
        reference_html=reference_html,
    )
    if not validation.passed:
        raise PipelineError("; ".join(validation.errors))

    final_output_path = reserve_output_path(build_result.title)
    shutil.copyfile(job_paths.stage4_shadowing_html_path, final_output_path)
    manifest["stages"]["shadowing_html"] = {
        "status": "completed",
        "output_files": [
            str(job_paths.stage4_shadowing_html_path),
            str(final_output_path),
        ],
        "cue_count": build_result.cue_count,
        "takeaway_count": build_result.takeaway_count,
        "validation": {
            "passed": validation.passed,
            "cue_count": validation.cue_count,
            "ruby_count": validation.ruby_count,
        },
    }
    write_manifest(job_paths.manifest_path, manifest)
    return final_output_path, validation


def _emit_progress(
    progress_callback: ProgressCallback,
    *,
    stage: str,
    status: str,
    message: str,
    stage_index: int = 0,
    completed: int | None = None,
    total: int | None = None,
    job_id: str | None = None,
) -> None:
    if progress_callback is None:
        return
    progress_callback(
        ProgressUpdate(
            stage=stage,
            status=status,
            message=message,
            stage_index=stage_index,
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
    manifest["last_stage"] = stage_name
    manifest["last_progress_message"] = message
    write_manifest(job_paths.manifest_path, manifest)


def _stage_index(stage_name: str) -> int:
    order = {
        "transcript": 1,
        "structure": 2,
        "base_html": 3,
        "shadowing_html": 4,
    }
    return order.get(stage_name, 0)


def _stage_label(stage_name: str) -> str:
    labels = {
        "pipeline": "Pipeline",
        "transcript": "Transcript acquisition",
        "structure": "Transcript structuring",
        "base_html": "Base HTML rendering",
        "shadowing_html": "Shadowing HTML build",
    }
    return labels.get(stage_name, stage_name.replace("_", " ").title())
