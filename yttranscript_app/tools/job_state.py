"""Filesystem layout and manifest helpers for yttranscript_app."""

from __future__ import annotations

import json
import pathlib
import time
import uuid
from dataclasses import dataclass
import re

APP_DIR = pathlib.Path(__file__).resolve().parent.parent
OUTPUT_DIR = APP_DIR / "Output"
WORK_DIR = APP_DIR / "Work"


@dataclass(frozen=True)
class JobPaths:
    """Filesystem layout for one yttranscript_app pipeline execution."""

    job_id: str
    job_dir: pathlib.Path
    manifest_path: pathlib.Path
    qa_summary_path: pathlib.Path
    stage0_request_path: pathlib.Path
    stage1_transcript_path: pathlib.Path
    stage2_structure_json_path: pathlib.Path
    stage2_structured_md_path: pathlib.Path
    stage3_base_html_path: pathlib.Path
    stage4_shadowing_html_path: pathlib.Path


def slugify_filename(value: str, *, max_length: int = 120) -> str:
    """Create a filesystem-safe slug without silently returning an empty string."""
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", value).strip("-")
    cleaned = re.sub(r"-{2,}", "-", cleaned)
    return cleaned[:max_length] or "shadowing-page"


def make_job_paths() -> JobPaths:
    """Create a unique work directory for a yttranscript_app job."""
    WORK_DIR.mkdir(parents=True, exist_ok=True)
    job_id = f"{time.strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:8]}"
    job_dir = WORK_DIR / job_id
    job_dir.mkdir(parents=True, exist_ok=False)
    return JobPaths(
        job_id=job_id,
        job_dir=job_dir,
        manifest_path=job_dir / "manifest.json",
        qa_summary_path=job_dir / "qa_summary.json",
        stage0_request_path=job_dir / "stage0_request.json",
        stage1_transcript_path=job_dir / "stage1_transcript.txt",
        stage2_structure_json_path=job_dir / "stage2_structure.json",
        stage2_structured_md_path=job_dir / "stage2_structured.md",
        stage3_base_html_path=job_dir / "stage3_base.html",
        stage4_shadowing_html_path=job_dir / "stage4_shadowing.html",
    )


def initialize_manifest(
    job_paths: JobPaths,
    *,
    source_url: str,
    video_id: str,
    language_hint: str | None,
) -> dict[str, object]:
    """Create the initial manifest for one pipeline execution."""
    manifest: dict[str, object] = {
        "job_id": job_paths.job_id,
        "created_at_epoch": time.time(),
        "source_url": source_url,
        "video_id": video_id,
        "language_hint": language_hint,
        "last_run_status": "pending",
        "stages": {
            "request": {"status": "completed", "output_file": str(job_paths.stage0_request_path)},
            "transcript": {"status": "pending"},
            "structure": {"status": "pending"},
            "base_html": {"status": "pending"},
            "shadowing_html": {"status": "pending"},
        },
    }
    write_manifest(job_paths.manifest_path, manifest)
    return manifest


def write_manifest(path: pathlib.Path, manifest: dict[str, object]) -> None:
    """Persist the manifest to disk."""
    path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def reserve_output_path(title: str) -> pathlib.Path:
    """Return a unique final output path in Output/ without overwriting existing files."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    slug = slugify_filename(title)
    candidate = OUTPUT_DIR / f"{slug}.html"
    counter = 1
    while candidate.exists():
        candidate = OUTPUT_DIR / f"{slug}-{counter}.html"
        counter += 1
    return candidate


def write_qa_summary(path: pathlib.Path, summary: dict[str, object]) -> None:
    """Persist a final QA summary beside the job manifest."""
    path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

