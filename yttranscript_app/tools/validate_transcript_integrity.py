#!/usr/bin/env python3
"""Validate that a structured transcript preserves the raw transcript cues."""

from __future__ import annotations

import argparse
import difflib
import re
import sys
from dataclasses import dataclass
from pathlib import Path


SUMMARY_HEADING = "## Key Takeaways"
TRANSCRIPT_HEADING = "## Structured Transcript"
SECTION_RE = re.compile(r"^### Section \d+:\s+.+$")
CUE_RE = re.compile(r"^\[\d{2}:\d{2}:\d{2}\.\d{3} --> \d{2}:\d{2}:\d{2}\.\d{3}\] .+$")


@dataclass(frozen=True)
class TranscriptIntegrityReport:
    passed: bool
    section_count: int
    found_summary: bool
    normalized_raw: str
    normalized_structured: str
    errors: tuple[str, ...]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Check that an optimized transcript preserves the raw transcript text."
    )
    parser.add_argument("raw", help="Path to the raw transcript file")
    parser.add_argument("optimized", help="Path to the optimized transcript file")
    parser.add_argument(
        "--require-summary",
        action="store_true",
        help="Fail if the optimized file does not contain a Key Takeaways section.",
    )
    parser.add_argument(
        "--require-sections",
        action="store_true",
        help="Fail if the optimized file does not contain at least one section subtitle.",
    )
    return parser.parse_args()


def read_text(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def extract_raw_cues(text: str) -> str:
    cue_lines = [line.strip() for line in text.splitlines() if CUE_RE.match(line.strip())]
    return "\n".join(cue_lines)


def extract_structured_transcript_body(text: str) -> tuple[str, int, bool]:
    lines = text.splitlines()
    transcript_lines: list[str] = []
    in_summary = False
    section_count = 0
    found_summary = False

    for line in lines:
        stripped = line.strip()

        if stripped == SUMMARY_HEADING:
            in_summary = True
            found_summary = True
            continue

        if in_summary or not stripped:
            continue

        if stripped == TRANSCRIPT_HEADING:
            continue

        if SECTION_RE.match(stripped):
            section_count += 1
            continue

        if CUE_RE.match(stripped):
            transcript_lines.append(stripped)

    return "\n".join(transcript_lines), section_count, found_summary


def first_difference(raw: str, optimized: str) -> str:
    matcher = difflib.SequenceMatcher(a=raw, b=optimized)
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue
        raw_context = raw[max(0, i1 - 60):min(len(raw), i2 + 60)]
        optimized_context = optimized[max(0, j1 - 60):min(len(optimized), j2 + 60)]
        return (
            f"First difference tag={tag}\n"
            f"Raw context: {raw_context!r}\n"
            f"Optimized context: {optimized_context!r}"
        )
    return "The normalized transcript differs, but no localized diff was found."


def validate_transcript_integrity(
    raw_text: str,
    optimized_text: str,
    *,
    require_summary: bool = True,
    require_sections: bool = True,
) -> TranscriptIntegrityReport:
    structured_body, section_count, found_summary = extract_structured_transcript_body(optimized_text)
    raw_normalized = normalize(extract_raw_cues(raw_text))
    optimized_normalized = normalize(structured_body)

    errors: list[str] = []

    if require_sections and section_count == 0:
        errors.append("No section subtitles matching '### Section N: <subtitle>' were found.")

    if require_summary and not found_summary:
        errors.append("No '## Key Takeaways' section was found.")

    if raw_normalized != optimized_normalized:
        errors.append("Transcript content changed or became incomplete.")
        errors.append(first_difference(raw_normalized, optimized_normalized))

    return TranscriptIntegrityReport(
        passed=not errors,
        section_count=section_count,
        found_summary=found_summary,
        normalized_raw=raw_normalized,
        normalized_structured=optimized_normalized,
        errors=tuple(errors),
    )


def main() -> int:
    args = parse_args()
    report = validate_transcript_integrity(
        read_text(args.raw),
        read_text(args.optimized),
        require_summary=args.require_summary,
        require_sections=args.require_sections,
    )

    if not report.passed:
        for error in report.errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1

    print("Transcript integrity check passed.")
    print(f"Sections found: {report.section_count}")
    print(f"Summary found: {'yes' if report.found_summary else 'no'}")
    print(f"Normalized transcript length: {len(report.normalized_structured)} characters")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
