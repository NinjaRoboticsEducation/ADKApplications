#!/usr/bin/env python3
"""Generate complete timestamped YouTube transcripts for shadowing practice."""

from __future__ import annotations

import argparse
import html
import importlib.util
import json
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional, Sequence, Tuple

DEFAULT_MIN_COVERAGE = 0.98
DEFAULT_MAX_EDGE_GAP = 3.0
DEFAULT_MAX_INTERNAL_GAP = 12.0
SUPPORTED_CAPTION_EXTS = ("json3", "vtt")
CAPTION_EXT_ORDER = {ext: index for index, ext in enumerate(SUPPORTED_CAPTION_EXTS)}


class TranscriptError(RuntimeError):
    """Raised when a complete transcript cannot be produced."""


@dataclass
class Segment:
    start: float
    end: float
    text: str


@dataclass
class TrackChoice:
    source: str
    language: str
    ext: str
    url: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate a timestamped YouTube transcript and reject incomplete coverage."
    )
    parser.add_argument("url", help="YouTube video URL")
    parser.add_argument(
        "--output",
        help="Output file path. Defaults to ./transcripts/<video-id>-<title>.txt",
    )
    parser.add_argument(
        "--lang",
        help="Preferred source language code, for example en, ja, or en-US",
    )
    parser.add_argument(
        "--force-asr",
        action="store_true",
        help="Skip subtitles and transcribe the full audio with Whisper.",
    )
    parser.add_argument(
        "--skip-asr",
        action="store_true",
        help="Do not use Whisper fallback if subtitles are incomplete.",
    )
    parser.add_argument(
        "--accept-incomplete",
        action="store_true",
        help="Write the best transcript available even if completeness checks fail.",
    )
    parser.add_argument(
        "--stdout",
        action="store_true",
        help="Print the transcript to stdout after writing the file.",
    )
    parser.add_argument(
        "--whisper-model",
        default="medium",
        help="Whisper model to use for ASR fallback. Default: medium",
    )
    parser.add_argument(
        "--min-coverage",
        type=float,
        default=DEFAULT_MIN_COVERAGE,
        help=f"Minimum acceptable runtime coverage. Default: {DEFAULT_MIN_COVERAGE}",
    )
    parser.add_argument(
        "--max-edge-gap",
        type=float,
        default=DEFAULT_MAX_EDGE_GAP,
        help=f"Maximum allowed gap at the start or end. Default: {DEFAULT_MAX_EDGE_GAP}",
    )
    parser.add_argument(
        "--max-internal-gap",
        type=float,
        default=DEFAULT_MAX_INTERNAL_GAP,
        help=f"Maximum allowed unexplained internal gap. Default: {DEFAULT_MAX_INTERNAL_GAP}",
    )
    parser.add_argument(
        "--max-chars",
        type=int,
        default=84,
        help="Maximum characters per transcript cue before splitting. Default: 84",
    )
    return parser.parse_args()


def require_command(name: str) -> None:
    if shutil.which(name):
        return
    raise TranscriptError(f"Required command not found: {name}")


def run_command(
    args: Sequence[str],
    *,
    capture_output: bool = True,
    check: bool = True,
) -> subprocess.CompletedProcess:
    completed = subprocess.run(
        args,
        text=True,
        capture_output=capture_output,
        check=False,
    )
    if check and completed.returncode != 0:
        stderr = (completed.stderr or "").strip()
        stdout = (completed.stdout or "").strip()
        message = stderr or stdout or "command failed"
        raise TranscriptError(f"{' '.join(args)}\n{message}")
    return completed


def load_metadata(url: str) -> dict:
    require_command("yt-dlp")
    completed = run_command(
        ["yt-dlp", "--dump-single-json", "--skip-download", "--no-warnings", url]
    )
    try:
        return json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise TranscriptError(f"Could not parse yt-dlp metadata: {exc}") from exc


def sanitize_filename(value: str, max_length: int = 80) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", value).strip("-")
    cleaned = re.sub(r"-{2,}", "-", cleaned)
    return cleaned[:max_length] or "transcript"


def parse_timestamp(value: str) -> float:
    text = value.strip().replace(",", ".")
    parts = text.split(":")
    if len(parts) == 2:
        hours = 0
        minutes, seconds = parts
    elif len(parts) == 3:
        hours, minutes, seconds = parts
    else:
        raise TranscriptError(f"Unsupported timestamp: {value}")
    return int(hours) * 3600 + int(minutes) * 60 + float(seconds)


def format_timestamp(seconds: float) -> str:
    total_ms = max(0, int(round(seconds * 1000)))
    hours, remainder = divmod(total_ms, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    secs, ms = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}.{ms:03d}"


def clean_text(value: str) -> str:
    text = html.unescape(value)
    text = re.sub(r"<[^>]+>", "", text)
    text = text.replace("\n", " ").replace("\r", " ")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def language_variants(code: Optional[str]) -> List[str]:
    if not code:
        return []
    lowered = code.lower()
    variants = [lowered]
    if "-" in lowered:
        variants.append(lowered.split("-", 1)[0])
    return variants


def language_score(language: str, requested: Optional[str], hinted: Optional[str]) -> Tuple[int, int]:
    lowered = language.lower()
    requested_variants = language_variants(requested)
    hinted_variants = language_variants(hinted)
    if lowered in requested_variants:
        return (0, 0)
    if lowered.split("-", 1)[0] in requested_variants:
        return (0, 1)
    if lowered in hinted_variants:
        return (1, 0)
    if lowered.split("-", 1)[0] in hinted_variants:
        return (1, 1)
    return (2, 0)


def choose_track(metadata: dict, requested_lang: Optional[str]) -> Optional[TrackChoice]:
    hinted_language = metadata.get("language") or metadata.get("original_language")
    best_score = None
    best_choice = None
    for source_name, source_map in (
        ("manual", metadata.get("subtitles") or {}),
        ("auto", metadata.get("automatic_captions") or {}),
    ):
        for language, formats in source_map.items():
            if "live_chat" in language:
                continue
            for fmt in formats:
                ext = (fmt.get("ext") or "").lower()
                url = fmt.get("url")
                if not url or ext not in CAPTION_EXT_ORDER:
                    continue
                score = (
                    0 if source_name == "manual" else 1,
                    *language_score(language, requested_lang, hinted_language),
                    CAPTION_EXT_ORDER[ext],
                )
                if best_score is None or score < best_score:
                    best_score = score
                    best_choice = TrackChoice(
                        source=source_name,
                        language=language,
                        ext=ext,
                        url=url,
                    )
    return best_choice


def download_track(track: TrackChoice, path: Path) -> Path:
    request = urllib.request.Request(track.url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(request) as response:
        path.write_bytes(response.read())
    return path


def parse_json3(path: Path) -> List[Segment]:
    data = json.loads(path.read_text(encoding="utf-8"))
    raw_segments = []
    for event in data.get("events") or []:
        start_ms = event.get("tStartMs")
        if start_ms is None:
            continue
        text = clean_text("".join(seg.get("utf8", "") for seg in event.get("segs") or []))
        if not text:
            continue
        duration_ms = event.get("dDurationMs")
        end = None
        if duration_ms is not None:
            end = (start_ms + duration_ms) / 1000.0
        raw_segments.append((start_ms / 1000.0, end, text))

    segments: List[Segment] = []
    for index, (start, end, text) in enumerate(raw_segments):
        if end is None or end <= start:
            next_start = raw_segments[index + 1][0] if index + 1 < len(raw_segments) else start + 2.0
            end = max(start + 0.25, next_start)
        segments.append(Segment(start=start, end=end, text=text))
    return segments


def parse_vtt(path: Path) -> List[Segment]:
    lines = path.read_text(encoding="utf-8").splitlines()
    segments: List[Segment] = []
    index = 0
    while index < len(lines):
        current = lines[index].strip().lstrip("\ufeff")
        if not current or current in {"WEBVTT"} or current.startswith("NOTE") or current.startswith("Kind:") or current.startswith("Language:"):
            index += 1
            continue
        if "-->" not in current:
            if index + 1 < len(lines) and "-->" in lines[index + 1]:
                index += 1
                current = lines[index].strip()
            else:
                index += 1
                continue
        if "-->" not in current:
            index += 1
            continue

        start_raw, end_raw = current.split("-->", 1)
        start = parse_timestamp(start_raw.split()[0])
        end = parse_timestamp(end_raw.strip().split()[0])
        index += 1

        cue_lines = []
        while index < len(lines) and lines[index].strip():
            cue_lines.append(lines[index].rstrip())
            index += 1

        text = clean_text(" ".join(cue_lines))
        if text:
            segments.append(Segment(start=start, end=end, text=text))
        index += 1
    return segments


def parse_track(path: Path) -> List[Segment]:
    if path.suffix.lower() == ".json3":
        return parse_json3(path)
    if path.suffix.lower() == ".vtt":
        return parse_vtt(path)
    raise TranscriptError(f"Unsupported caption format: {path.suffix}")


def trim_token_overlap(previous: str, current: str) -> str:
    previous_tokens = previous.split()
    current_tokens = current.split()
    if not previous_tokens or not current_tokens:
        return current

    max_overlap = min(len(previous_tokens), len(current_tokens))
    for size in range(max_overlap, 0, -1):
        if previous_tokens[-size:] == current_tokens[:size]:
            remainder = " ".join(current_tokens[size:])
            return remainder.strip() or current
    return current


def split_text_chunks(text: str, max_chars: int) -> List[str]:
    phrase_parts = re.findall(r"[^,.!?;:。！？、]+[,.!?;:。！？、]?", text)
    parts = [clean_text(part) for part in phrase_parts if clean_text(part)]
    if not parts:
        parts = [text]

    chunks: List[str] = []
    current = ""
    for part in parts:
        candidate = f"{current} {part}".strip() if current else part
        if len(candidate) <= max_chars:
            current = candidate
            continue
        if current:
            chunks.append(current)
        if len(part) <= max_chars:
            current = part
            continue
        words = part.split()
        current_word_chunk = ""
        for word in words:
            candidate = f"{current_word_chunk} {word}".strip() if current_word_chunk else word
            if len(candidate) <= max_chars:
                current_word_chunk = candidate
                continue
            if current_word_chunk:
                chunks.append(current_word_chunk)
            current_word_chunk = word
        current = current_word_chunk
    if current:
        chunks.append(current)
    return chunks or [text]


def split_segment(segment: Segment, max_chars: int) -> List[Segment]:
    if len(segment.text) <= max_chars or segment.end - segment.start <= 2.0:
        return [segment]

    chunks = split_text_chunks(segment.text, max_chars)
    if len(chunks) == 1:
        return [segment]

    weights = [max(len(chunk), 1) for chunk in chunks]
    total_weight = sum(weights)
    duration = max(segment.end - segment.start, 0.25 * len(chunks))
    cursor = segment.start
    results: List[Segment] = []
    for index, chunk in enumerate(chunks):
        if index == len(chunks) - 1:
            chunk_end = segment.end
        else:
            chunk_duration = duration * (weights[index] / total_weight)
            chunk_end = min(segment.end, cursor + max(0.2, chunk_duration))
        results.append(Segment(start=cursor, end=chunk_end, text=chunk))
        cursor = chunk_end
    return results


def normalize_segments(segments: Iterable[Segment], max_chars: int) -> List[Segment]:
    ordered = sorted(
        (
            Segment(
                start=max(0.0, segment.start),
                end=max(segment.end, segment.start + 0.05),
                text=clean_text(segment.text),
            )
            for segment in segments
        ),
        key=lambda item: (item.start, item.end),
    )

    trimmed: List[Segment] = []
    for segment in ordered:
        if not segment.text:
            continue
        text = segment.text
        if trimmed:
            text = trim_token_overlap(trimmed[-1].text, text)
        if not text:
            continue
        trimmed.append(Segment(start=segment.start, end=segment.end, text=text))

    split_results: List[Segment] = []
    for segment in trimmed:
        split_results.extend(split_segment(segment, max_chars))
    return split_results


def coverage_report(segments: Sequence[Segment], duration: float) -> dict:
    if not segments:
        return {
            "coverage": 0.0,
            "first_gap": duration if duration else 0.0,
            "last_gap": duration if duration else 0.0,
            "max_internal_gap": duration if duration else 0.0,
        }

    intervals = sorted((segment.start, max(segment.end, segment.start)) for segment in segments)
    merged: List[Tuple[float, float]] = []
    for start, end in intervals:
        if not merged or start > merged[-1][1]:
            merged.append((start, end))
            continue
        merged[-1] = (merged[-1][0], max(merged[-1][1], end))

    covered = sum(end - start for start, end in merged)
    first_gap = max(0.0, merged[0][0])
    last_gap = max(0.0, duration - merged[-1][1]) if duration else 0.0
    max_gap = 0.0
    for previous, current in zip(merged, merged[1:]):
        max_gap = max(max_gap, current[0] - previous[1])

    coverage = covered / duration if duration > 0 else 1.0
    return {
        "coverage": coverage,
        "first_gap": first_gap,
        "last_gap": last_gap,
        "max_internal_gap": max_gap,
    }


def transcript_is_complete(report: dict, args: argparse.Namespace, duration: float) -> bool:
    if duration <= 0:
        return True
    return (
        report["coverage"] >= args.min_coverage
        and report["first_gap"] <= args.max_edge_gap
        and report["last_gap"] <= args.max_edge_gap
        and report["max_internal_gap"] <= args.max_internal_gap
    )


def describe_report(report: dict) -> str:
    return (
        f"coverage={report['coverage'] * 100:.1f}% "
        f"first_gap={report['first_gap']:.1f}s "
        f"last_gap={report['last_gap']:.1f}s "
        f"max_internal_gap={report['max_internal_gap']:.1f}s"
    )


def download_audio(url: str, tempdir: Path) -> Path:
    output_template = str(tempdir / "audio.%(ext)s")
    run_command(
        ["yt-dlp", "-f", "bestaudio/best", "-o", output_template, "--no-warnings", url],
        capture_output=True,
    )
    candidates = [
        path
        for path in tempdir.glob("audio.*")
        if path.suffix not in {".part", ".ytdl"}
    ]
    if not candidates:
        raise TranscriptError("yt-dlp downloaded no audio file for ASR fallback.")
    return max(candidates, key=lambda item: item.stat().st_size)


def detect_whisper_runner() -> List[str]:
    if shutil.which("whisper"):
        return ["whisper"]
    if importlib.util.find_spec("whisper") is not None:
        return [sys.executable, "-m", "whisper"]
    raise TranscriptError(
        "Whisper fallback is unavailable. Install `openai-whisper` and ensure `ffmpeg` is available."
    )


def transcribe_with_whisper(
    audio_path: Path,
    language: Optional[str],
    model: str,
    tempdir: Path,
) -> List[Segment]:
    runner = detect_whisper_runner()
    command = runner + [
        str(audio_path),
        "--task",
        "transcribe",
        "--model",
        model,
        "--output_format",
        "json",
        "--output_dir",
        str(tempdir),
        "--verbose",
        "False",
    ]
    if language:
        command.extend(["--language", language.split("-", 1)[0]])
    run_command(command)

    json_candidates = sorted(tempdir.glob("*.json"))
    if not json_candidates:
        raise TranscriptError("Whisper finished without producing a JSON transcript.")

    whisper_data = json.loads(json_candidates[0].read_text(encoding="utf-8"))
    segments = [
        Segment(
            start=float(item["start"]),
            end=float(item["end"]),
            text=clean_text(item["text"]),
        )
        for item in whisper_data.get("segments") or []
        if clean_text(item.get("text", ""))
    ]
    if not segments:
        raise TranscriptError("Whisper produced no transcript segments.")
    return segments


def default_output_path(metadata: dict) -> Path:
    video_id = sanitize_filename(str(metadata.get("id") or "video"))
    title = sanitize_filename(str(metadata.get("title") or video_id))
    return Path("transcripts") / f"{video_id}-{title}.txt"


def render_transcript(
    metadata: dict,
    source_label: str,
    language: Optional[str],
    report: dict,
    segments: Sequence[Segment],
) -> str:
    header = [
        f"# Title: {metadata.get('title') or 'Unknown'}",
        f"# URL: {metadata.get('webpage_url') or metadata.get('original_url') or ''}",
        f"# Source: {source_label}",
        f"# Language: {language or metadata.get('language') or metadata.get('original_language') or 'unknown'}",
        f"# Duration: {format_timestamp(float(metadata.get('duration') or 0.0))}",
        f"# QA: {describe_report(report)}",
        "",
    ]
    body = [
        f"[{format_timestamp(segment.start)} --> {format_timestamp(segment.end)}] {segment.text}"
        for segment in segments
    ]
    return "\n".join(header + body).rstrip() + "\n"


def write_output(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def main() -> int:
    args = parse_args()

    try:
        metadata = load_metadata(args.url)
        duration = float(metadata.get("duration") or 0.0)
        chosen_language = args.lang or metadata.get("language") or metadata.get("original_language")

        transcript_segments: List[Segment] = []
        source_label = ""
        report = coverage_report([], duration)

        with tempfile.TemporaryDirectory(prefix="yttranscript-") as temp_root:
            tempdir = Path(temp_root)
            if not args.force_asr:
                track = choose_track(metadata, args.lang)
                if track is not None:
                    track_path = tempdir / f"captions.{track.ext}"
                    download_track(track, track_path)
                    transcript_segments = normalize_segments(
                        parse_track(track_path),
                        args.max_chars,
                    )
                    chosen_language = track.language
                    source_label = f"{track.source} subtitles ({track.language}, {track.ext})"
                    report = coverage_report(transcript_segments, duration)
                    if not transcript_is_complete(report, args, duration) and not args.accept_incomplete:
                        transcript_segments = []

            if not transcript_segments:
                if args.skip_asr:
                    raise TranscriptError(
                        "Subtitle coverage failed completeness checks and ASR fallback is disabled."
                    )
                audio_path = download_audio(args.url, tempdir)
                transcript_segments = normalize_segments(
                    transcribe_with_whisper(
                        audio_path=audio_path,
                        language=chosen_language,
                        model=args.whisper_model,
                        tempdir=tempdir,
                    ),
                    args.max_chars,
                )
                source_label = f"whisper ASR ({args.whisper_model})"
                report = coverage_report(transcript_segments, duration)

        if not transcript_segments:
            raise TranscriptError("No transcript segments were produced.")

        if not transcript_is_complete(report, args, duration) and not args.accept_incomplete:
            raise TranscriptError(
                "Generated transcript still failed completeness checks: "
                f"{describe_report(report)}"
            )

        output_path = Path(args.output) if args.output else default_output_path(metadata)
        content = render_transcript(
            metadata=metadata,
            source_label=source_label,
            language=chosen_language,
            report=report,
            segments=transcript_segments,
        )
        write_output(output_path, content)
        print(f"Wrote transcript to {output_path}")
        print(describe_report(report))
        if args.stdout:
            print()
            sys.stdout.write(content)
        return 0
    except TranscriptError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
