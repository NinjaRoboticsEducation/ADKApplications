#!/usr/bin/env python3
"""Validate shadowing HTML for required embed and interaction features."""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import parse_qs, urlparse


REQUIRED_REFERENCE_FEATURES = (
    ("class", "hero"),
    ("class", "panel"),
    ("id", "runtime-warning"),
    ("class", "takeaways"),
    ("class", "transcript-section"),
    ("class", "cue"),
    ("id", "dictionary-popup"),
)
@dataclass(frozen=True)
class ShadowingHtmlValidationReport:
    passed: bool
    cue_count: int
    ruby_count: int
    errors: tuple[str, ...]


class _FeatureParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.class_tokens: set[str] = set()
        self.ids: set[str] = set()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_map = {key: value or "" for key, value in attrs}
        if attrs_map.get("id"):
            self.ids.add(attrs_map["id"])
        for class_name in attrs_map.get("class", "").split():
            if class_name:
                self.class_tokens.add(class_name)


def _extract_features(html_text: str) -> tuple[set[str], set[str]]:
    parser = _FeatureParser()
    parser.feed(html_text)
    return parser.class_tokens, parser.ids


def _has_reference_feature(
    feature: tuple[str, str],
    *,
    class_tokens: set[str],
    ids: set[str],
) -> bool:
    feature_type, value = feature
    if feature_type == "class":
        return value in class_tokens
    if feature_type == "id":
        return value in ids
    return False


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Check that a generated shadowing HTML file includes the required features."
    )
    parser.add_argument("html_path", help="Path to the generated HTML file")
    parser.add_argument(
        "--youtube-url",
        help="Optional YouTube URL to confirm the expected video id is embedded.",
    )
    parser.add_argument(
        "--reference-html",
        help="Optional reference HTML path for structural contract checks.",
    )
    return parser.parse_args()


def extract_youtube_id(url: str) -> str:
    parsed = urlparse(url)
    host = parsed.netloc.lower()
    path = parsed.path.strip("/")

    if host in {"youtu.be", "www.youtu.be"} and path:
        return path.split("/", 1)[0]

    if host.endswith("youtube.com") or host.endswith("youtube-nocookie.com"):
        if path == "watch":
            return parse_qs(parsed.query).get("v", [""])[0]
        if path.startswith(("embed/", "shorts/", "live/")):
            return path.split("/", 1)[1].split("/", 1)[0]
    return ""


def require(pattern: str, text: str, message: str) -> str | None:
    if re.search(pattern, text, re.IGNORECASE | re.DOTALL):
        return None
    return message


def validate_shadowing_html_content(
    html_text: str,
    *,
    youtube_url: str | None = None,
    reference_html: str | None = None,
) -> ShadowingHtmlValidationReport:
    errors: list[str] = []
    class_tokens, ids = _extract_features(html_text)

    checks = [
        (r"youtube\.com/embed/|iframe_api|YT\.Player", "Missing YouTube embed or iframe API markers."),
        (r'class="[^"]*\bcue\b[^"]*"[^>]*data-start="[^"]+"[^>]*data-end="[^"]+"', "Cue elements are missing data-start/data-end attributes."),
        (r'<ruby>.*?<rt>\[[0-9:.]+\s*(?:-->|--&gt;)\s*[0-9:.]+\]</rt>.*?</ruby>', "Cue markup is missing ruby/rt timestamp rendering."),
        (r"rt\s*\{[^}]*font-size:\s*0\.4em", "The <rt> style does not set font-size to 0.4em."),
        (r"is-active|activeCueIndex|updateActiveCue", "Active cue highlighting logic was not found."),
        (r"dictionaryapi\.dev/api/v2/entries/en/", "Dictionary API integration marker was not found."),
        (r"window\.location\.protocol\s*===\s*'file:'|IS_FILE_PROTOCOL", "The page does not appear to guard against file:// preview mode."),
        (r"widget_referrer|PAGE_HREF", "The page does not include widget_referrer handling for YouTube embeds."),
        (r"origin|PAGE_ORIGIN", "The page does not include origin handling for YouTube embeds."),
        (r"Content-Security-Policy", "Missing Content-Security-Policy metadata."),
        (r"Referrer-Policy", "Missing Referrer-Policy metadata."),
    ]

    for pattern, message in checks:
        error = require(pattern, html_text, message)
        if error:
            errors.append(error)

    if re.search(r"\.innerHTML\s*=", html_text):
        errors.append("Unsafe innerHTML writes were found in the page script.")

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

    english_cue_text_present = bool(
        re.search(
            r'<div class="cue"[^>]*>.*?[A-Za-z]{2,}.*?</div>',
            html_text,
            re.IGNORECASE | re.DOTALL,
        )
    )
    if english_cue_text_present and "dict-word" not in html_text:
        errors.append("Dictionary word spans were not added to cue text containing English words.")

    if youtube_url:
        expected_id = extract_youtube_id(youtube_url)
        if expected_id and expected_id not in html_text:
            errors.append("The expected YouTube video id was not found in the generated HTML.")

    if reference_html:
        reference_classes, reference_ids = _extract_features(reference_html)
        for feature in REQUIRED_REFERENCE_FEATURES:
            if not _has_reference_feature(
                feature,
                class_tokens=reference_classes,
                ids=reference_ids,
            ):
                continue
            if not _has_reference_feature(feature, class_tokens=class_tokens, ids=ids):
                feature_type, value = feature
                errors.append(
                    f"Missing structural contract feature from reference HTML: {feature_type}={value}"
                )
    return ShadowingHtmlValidationReport(
        passed=not errors,
        cue_count=cue_count,
        ruby_count=ruby_count,
        errors=tuple(errors),
    )


def main() -> int:
    args = parse_args()
    reference_html = None
    if args.reference_html:
        reference_html = Path(args.reference_html).read_text(encoding="utf-8")
    report = validate_shadowing_html_content(
        Path(args.html_path).read_text(encoding="utf-8"),
        youtube_url=args.youtube_url,
        reference_html=reference_html,
    )

    if not report.passed:
        for error in report.errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1

    print("Shadowing HTML validation passed.")
    print(f"Cue count: {report.cue_count}")
    print(f"Ruby count: {report.ruby_count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
