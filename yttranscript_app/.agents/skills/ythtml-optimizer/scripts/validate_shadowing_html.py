#!/usr/bin/env python3
"""Validate shadowing HTML for required embed and interaction features."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlparse


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Check that a generated shadowing HTML file includes the required features."
    )
    parser.add_argument("html_path", help="Path to the generated HTML file")
    parser.add_argument(
        "--youtube-url",
        help="Optional YouTube URL to confirm the expected video id is embedded.",
    )
    return parser.parse_args()


def extract_youtube_id(url: str) -> str:
    parsed = urlparse(url)
    host = parsed.netloc.lower()
    path = parsed.path.strip("/")

    if host in {"youtu.be", "www.youtu.be"} and path:
        return path.split("/", 1)[0]

    if host.endswith("youtube.com"):
        if path == "watch":
            return parse_qs(parsed.query).get("v", [""])[0]
        if path.startswith(("embed/", "shorts/", "live/")):
            return path.split("/", 1)[1]
    return ""


def require(pattern: str, text: str, message: str) -> str | None:
    if re.search(pattern, text, re.IGNORECASE | re.DOTALL):
        return None
    return message


def main() -> int:
    args = parse_args()
    html_text = Path(args.html_path).read_text(encoding="utf-8")
    errors: list[str] = []

    checks = [
        (r"youtube\.com/embed/|iframe_api|YT\.Player", "Missing YouTube embed or iframe API markers."),
        (r'class="[^"]*\bcue\b[^"]*"[^>]*data-start="[^"]+"[^>]*data-end="[^"]+"', "Cue elements are missing data-start/data-end attributes."),
        (r'<ruby>.*?<rt>\[[0-9:.]+\s*(?:-->|--&gt;)\s*[0-9:.]+\]</rt>.*?</ruby>', "Cue markup is missing ruby/rt timestamp rendering."),
        (r"rt\s*\{[^}]*font-size:\s*0\.4em", "The <rt> style does not set font-size to 0.4em."),
        (r"is-active|activeCueIndex|updateActiveCue", "Active cue highlighting logic was not found."),
        (r"dictionaryapi\.dev/api/v2/entries/en/", "Dictionary API integration marker was not found."),
        (r"dict-word", "Dictionary word interaction markers were not found."),
        (r"window\.location\.protocol\s*===\s*'file:'|IS_FILE_PROTOCOL", "The page does not appear to guard against file:// preview mode."),
        (r"widget_referrer|PAGE_HREF", "The page does not include widget_referrer handling for YouTube embeds."),
        (r"origin|PAGE_ORIGIN", "The page does not include origin handling for YouTube embeds."),
    ]

    for pattern, message in checks:
        error = require(pattern, html_text, message)
        if error:
            errors.append(error)

    cue_count = len(
        re.findall(
            r'class="[^"]*\bcue\b[^"]*"[^>]*data-start="[^"]+"[^>]*data-end="[^"]+"',
            html_text,
            re.IGNORECASE,
        )
    )
    ruby_count = len(re.findall(r"<ruby>", html_text, re.IGNORECASE))

    if cue_count == 0:
        errors.append("No synchronized cues were found in the HTML.")

    if ruby_count < cue_count:
        errors.append("Not every cue appears to contain ruby markup.")

    if args.youtube_url:
        expected_id = extract_youtube_id(args.youtube_url)
        if expected_id and expected_id not in html_text:
            errors.append("The expected YouTube video id was not found in the generated HTML.")

    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1

    print("Shadowing HTML validation passed.")
    print(f"Cue count: {cue_count}")
    print(f"Ruby count: {ruby_count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
