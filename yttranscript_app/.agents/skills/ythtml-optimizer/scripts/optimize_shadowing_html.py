#!/usr/bin/env python3
"""Transform transcript HTML into a synchronized shadowing page."""

from __future__ import annotations

import argparse
import html
import re
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from typing import Dict, List, Optional
from urllib.parse import parse_qs, urlparse

TIMESTAMP_RE = re.compile(
    r"\[(\d{2}:\d{2}:\d{2}\.\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2}\.\d{3})\]"
)
WORD_RE = re.compile(r"[A-Za-z]+(?:['-][A-Za-z]+)*")
BLOCK_TAGS = {
    "article",
    "aside",
    "blockquote",
    "br",
    "div",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "header",
    "li",
    "main",
    "p",
    "section",
}


class OptimizationError(RuntimeError):
    """Raised when the transcript HTML cannot be optimized safely."""


@dataclass
class Cue:
    section: str
    start_raw: str
    end_raw: str
    start_seconds: float
    end_seconds: float
    text: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Optimize transcript HTML into a synchronized shadowing page."
    )
    parser.add_argument("input_html", help="Source transcript HTML file")
    parser.add_argument("youtube_url", help="Source YouTube URL")
    parser.add_argument(
        "--output",
        help="Output HTML path. Defaults to <sanitized-title>.html in the current directory.",
    )
    parser.add_argument(
        "--title",
        help="Video title override. Defaults to the input HTML title or file stem.",
    )
    return parser.parse_args()


def sanitize_filename(value: str, max_length: int = 120) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", value).strip("-")
    cleaned = re.sub(r"-{2,}", "-", cleaned)
    return (cleaned[:max_length] or "shadowing-page") + ".html"


def clean_text(value: str) -> str:
    text = html.unescape(value)
    text = text.replace("\xa0", " ")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def parse_timestamp(value: str) -> float:
    hours, minutes, seconds = value.split(":")
    return int(hours) * 3600 + int(minutes) * 60 + float(seconds)


def extract_youtube_id(url: str) -> str:
    parsed = urlparse(url)
    host = parsed.netloc.lower()
    path = parsed.path.strip("/")

    if host in {"youtu.be", "www.youtu.be"} and path:
        return path.split("/", 1)[0]

    if host.endswith("youtube.com"):
        if path == "watch":
            video_id = parse_qs(parsed.query).get("v", [""])[0]
            if video_id:
                return video_id
        if path.startswith("embed/"):
            return path.split("/", 1)[1]
        if path.startswith("shorts/"):
            return path.split("/", 1)[1]
        if path.startswith("live/"):
            return path.split("/", 1)[1]

    raise OptimizationError(f"Unsupported YouTube URL: {url}")


class TranscriptHTMLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.page_title: Optional[str] = None
        self._title_parts: List[str] = []
        self._title_depth = 0

        self._heading_tag: Optional[str] = None
        self._heading_parts: List[str] = []
        self.current_section = "Transcript"
        self.in_takeaways = False

        self._summary_item_parts: Optional[List[str]] = None
        self.summary_items: List[str] = []

        self.current_cue: Optional[Dict[str, object]] = None
        self._cue_depth = 0
        self._cue_modes: List[Optional[str]] = []
        self.cues: List[Cue] = []

    @staticmethod
    def _class_tokens(attrs: Dict[str, str]) -> set[str]:
        return {token for token in attrs.get("class", "").split() if token}

    def handle_starttag(self, tag: str, attrs_list: list[tuple[str, Optional[str]]]) -> None:
        attrs = {key: value or "" for key, value in attrs_list}
        class_tokens = self._class_tokens(attrs)

        if tag == "title":
            self._title_depth += 1
            return

        if self.current_cue is not None:
            self._cue_depth += 1
            mode = None
            if "cue-time" in class_tokens:
                mode = "time"
            elif "cue-text" in class_tokens:
                mode = "text"
            self._cue_modes.append(mode)
            if tag == "br":
                self._append_cue_text(" ")
            return

        if tag in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            self._heading_tag = tag
            self._heading_parts = []
            return

        if self.in_takeaways and tag == "li":
            self._summary_item_parts = []
            return

        if "cue" in class_tokens or ("data-start" in attrs and "data-end" in attrs):
            self.current_cue = {
                "attrs": attrs,
                "all_parts": [],
                "time_parts": [],
                "text_parts": [],
                "section": self.current_section,
            }
            self._cue_depth = 1
            self._cue_modes = [None]
            return

    def handle_endtag(self, tag: str) -> None:
        if self._title_depth and tag == "title":
            self._title_depth -= 1
            title = clean_text("".join(self._title_parts))
            if title and not self.page_title:
                self.page_title = title
            self._title_parts = []
            return

        if self.current_cue is not None:
            if self._cue_modes:
                self._cue_modes.pop()
            self._cue_depth -= 1
            if self._cue_depth == 0:
                self._finalize_cue()
                self.current_cue = None
                self._cue_modes = []
            return

        if self._heading_tag == tag:
            heading = clean_text("".join(self._heading_parts))
            self._finalize_heading(tag, heading)
            self._heading_tag = None
            self._heading_parts = []
            return

        if self._summary_item_parts is not None and tag == "li":
            item = clean_text("".join(self._summary_item_parts))
            if item:
                self.summary_items.append(item)
            self._summary_item_parts = None

    def handle_data(self, data: str) -> None:
        if self._title_depth:
            self._title_parts.append(data)
            return

        if self.current_cue is not None:
            mode = next((item for item in reversed(self._cue_modes) if item), None)
            if mode == "time":
                self.current_cue["time_parts"].append(data)
            elif mode == "text":
                self.current_cue["text_parts"].append(data)
            else:
                self.current_cue["all_parts"].append(data)
            return

        if self._heading_tag is not None:
            self._heading_parts.append(data)
            return

        if self._summary_item_parts is not None:
            self._summary_item_parts.append(data)

    def _append_cue_text(self, text: str) -> None:
        if self.current_cue is None:
            return
        self.current_cue["all_parts"].append(text)
        self.current_cue["text_parts"].append(text)

    def _finalize_heading(self, tag: str, heading: str) -> None:
        if not heading:
            return
        if tag == "h1" and not self.page_title:
            self.page_title = heading
            return

        lowered = heading.lower()
        if "key takeaways" in lowered:
            self.in_takeaways = True
            return

        if "structured transcript" in lowered or lowered == "transcript":
            self.in_takeaways = False
            return

        if tag in {"h2", "h3", "h4", "h5", "h6"}:
            self.in_takeaways = False
            self.current_section = heading

    def _finalize_cue(self) -> None:
        if self.current_cue is None:
            return
        attrs = self.current_cue["attrs"]
        time_text = clean_text("".join(self.current_cue["time_parts"]))
        body_text = clean_text("".join(self.current_cue["text_parts"]))
        all_text = clean_text("".join(self.current_cue["all_parts"]))

        start_raw = end_raw = None
        start_seconds = end_seconds = None

        timestamp_match = TIMESTAMP_RE.search(time_text or all_text)
        if timestamp_match:
            start_raw, end_raw = timestamp_match.groups()
            start_seconds = parse_timestamp(start_raw)
            end_seconds = parse_timestamp(end_raw)

        if start_seconds is None and attrs.get("data-start") and attrs.get("data-end"):
            start_seconds = float(attrs["data-start"])
            end_seconds = float(attrs["data-end"])
            start_raw = seconds_to_timestamp(start_seconds)
            end_raw = seconds_to_timestamp(end_seconds)

        if not body_text and timestamp_match:
            body_text = clean_text(TIMESTAMP_RE.sub("", all_text, count=1))
        elif not body_text:
            body_text = all_text

        if start_seconds is None or end_seconds is None or not body_text:
            return

        self.cues.append(
            Cue(
                section=str(self.current_cue["section"] or "Transcript"),
                start_raw=start_raw or seconds_to_timestamp(start_seconds),
                end_raw=end_raw or seconds_to_timestamp(end_seconds),
                start_seconds=start_seconds,
                end_seconds=end_seconds,
                text=body_text,
            )
        )


class VisibleTextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: List[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, Optional[str]]]) -> None:
        if tag in BLOCK_TAGS:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in BLOCK_TAGS:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        self.parts.append(data)


def seconds_to_timestamp(seconds: float) -> str:
    total_ms = max(0, int(round(seconds * 1000)))
    hours, remainder = divmod(total_ms, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    secs, ms = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}.{ms:03d}"


def fallback_cues_from_text(html_text: str) -> List[Cue]:
    extractor = VisibleTextExtractor()
    extractor.feed(html_text)
    cues: List[Cue] = []
    current_section = "Transcript"
    for line in extractor.parts:
        for raw_line in line.splitlines():
            line_text = clean_text(raw_line)
            if not line_text:
                continue
            lowered = line_text.lower()
            if lowered == "key takeaways":
                break
            if lowered.startswith("section "):
                current_section = line_text
                continue
            match = TIMESTAMP_RE.match(line_text)
            if not match:
                continue
            start_raw, end_raw = match.groups()
            cue_text = clean_text(line_text[match.end() :])
            if not cue_text:
                continue
            cues.append(
                Cue(
                    section=current_section,
                    start_raw=start_raw,
                    end_raw=end_raw,
                    start_seconds=parse_timestamp(start_raw),
                    end_seconds=parse_timestamp(end_raw),
                    text=cue_text,
                )
            )
    return cues


def parse_input_html(path: Path) -> tuple[str, List[Cue], List[str]]:
    raw = path.read_text(encoding="utf-8")
    parser = TranscriptHTMLParser()
    parser.feed(raw)
    cues = parser.cues or fallback_cues_from_text(raw)
    if not cues:
        raise OptimizationError(
            "No parseable timestamped cues were found in the input HTML. "
            "Expected .cue markup or visible [start --> end] transcript lines."
        )
    title = parser.page_title or path.stem
    return title, cues, parser.summary_items


def wrap_english_words(text: str) -> str:
    parts: List[str] = []
    cursor = 0
    for match in WORD_RE.finditer(text):
        parts.append(html.escape(text[cursor : match.start()]))
        word = match.group(0)
        escaped = html.escape(word)
        parts.append(
            f'<span class="dict-word" data-word="{html.escape(word.lower(), quote=True)}">{escaped}</span>'
        )
        cursor = match.end()
    parts.append(html.escape(text[cursor:]))
    return "".join(parts)


def render_sections(cues: List[Cue]) -> str:
    grouped: Dict[str, List[Cue]] = {}
    ordered_sections: List[str] = []
    for cue in cues:
        if cue.section not in grouped:
            grouped[cue.section] = []
            ordered_sections.append(cue.section)
        grouped[cue.section].append(cue)

    section_chunks: List[str] = []
    cue_index = 0
    for section_name in ordered_sections:
        cue_html: List[str] = []
        for cue in grouped[section_name]:
            time_label = f"[{cue.start_raw} --> {cue.end_raw}]"
            cue_html.append(
                (
                    f'<div class="cue" id="cue-{cue_index:05d}" '
                    f'data-start="{cue.start_seconds:.3f}" '
                    f'data-end="{cue.end_seconds:.3f}" tabindex="0">'
                    f"<ruby>{wrap_english_words(cue.text)}"
                    f"<rt>{html.escape(time_label)}</rt></ruby>"
                    "</div>"
                )
            )
            cue_index += 1
        section_chunks.append(
            "<section class=\"transcript-section\">"
            f"<h2 class=\"section-title\">{html.escape(section_name)}</h2>"
            "<div class=\"cue-list\">"
            + "".join(cue_html)
            + "</div></section>"
        )
    return "".join(section_chunks)


def render_takeaways(items: List[str]) -> str:
    if not items:
        return ""
    bullets = "".join(
        f"<li>{html.escape(item)}</li>"
        for item in items
    )
    return (
        '<aside class="takeaways" aria-labelledby="takeaways-title">'
        '<h2 id="takeaways-title">Key Takeaways</h2>'
        f"<ul>{bullets}</ul>"
        "</aside>"
    )


def build_html(title: str, youtube_url: str, video_id: str, cues: List[Cue], takeaways: List[str]) -> str:
    sections_html = render_sections(cues)
    takeaways_html = render_takeaways(takeaways)
    safe_title = html.escape(title)
    safe_url = html.escape(youtube_url, quote=True)
    escaped_url_text = html.escape(youtube_url)

    return (
        "<!doctype html>\n"
        "<html lang=\"en\">\n"
        "<head>\n"
        "  <meta charset=\"utf-8\">\n"
        "  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">\n"
        f"  <title>{safe_title}</title>\n"
        "  <style>\n"
        "    :root {\n"
        "      color-scheme: light;\n"
        "      --page: #f7f4ee;\n"
        "      --panel: rgba(255, 255, 255, 0.92);\n"
        "      --ink: #1f1d18;\n"
        "      --muted: #6d655a;\n"
        "      --accent: #c56a2d;\n"
        "      --accent-soft: rgba(197, 106, 45, 0.14);\n"
        "      --line: rgba(31, 29, 24, 0.12);\n"
        "      --shadow: 0 18px 44px rgba(49, 38, 23, 0.14);\n"
        "    }\n"
        "    * { box-sizing: border-box; }\n"
        "    body {\n"
        "      margin: 0;\n"
        "      font-family: \"Noto Sans\", \"Noto Sans JP\", \"Segoe UI\", sans-serif;\n"
        "      background: radial-gradient(circle at top, #fffaf3 0%, var(--page) 55%, #efe6d9 100%);\n"
        "      color: var(--ink);\n"
        "      line-height: 1.7;\n"
        "    }\n"
        "    a { color: var(--accent); }\n"
        "    .shell {\n"
        "      width: min(1320px, calc(100vw - 32px));\n"
        "      margin: 0 auto;\n"
        "      padding: 28px 0 48px;\n"
        "    }\n"
        "    .hero, .panel, .takeaways, .transcript-section, .dictionary-popup {\n"
        "      background: var(--panel);\n"
        "      backdrop-filter: blur(14px);\n"
        "      border: 1px solid var(--line);\n"
        "      box-shadow: var(--shadow);\n"
        "    }\n"
        "    .hero {\n"
        "      border-radius: 28px;\n"
        "      padding: 28px;\n"
        "      margin-bottom: 24px;\n"
        "    }\n"
        "    .eyebrow {\n"
        "      font-size: 0.8rem;\n"
        "      letter-spacing: 0.18em;\n"
        "      text-transform: uppercase;\n"
        "      color: var(--muted);\n"
        "      margin: 0 0 10px;\n"
        "    }\n"
        "    h1 {\n"
        "      margin: 0 0 10px;\n"
        "      font-size: clamp(2rem, 3vw, 3.4rem);\n"
        "      line-height: 1.1;\n"
        "    }\n"
        "    .meta {\n"
        "      display: flex;\n"
        "      flex-wrap: wrap;\n"
        "      gap: 12px 20px;\n"
        "      color: var(--muted);\n"
        "      font-size: 0.95rem;\n"
        "    }\n"
        "    .layout {\n"
        "      display: grid;\n"
        "      grid-template-columns: minmax(320px, 0.95fr) minmax(0, 1.15fr);\n"
        "      gap: 24px;\n"
        "      align-items: start;\n"
        "    }\n"
        "    .panel {\n"
        "      position: sticky;\n"
        "      top: 20px;\n"
        "      border-radius: 24px;\n"
        "      padding: 18px;\n"
        "    }\n"
        "    .player-shell {\n"
        "      aspect-ratio: 16 / 9;\n"
        "      overflow: hidden;\n"
        "      border-radius: 18px;\n"
        "      background: #0f1115;\n"
        "      margin-bottom: 14px;\n"
        "    }\n"
        "    .player-shell iframe,\n"
        "    .player-shell #player,\n"
        "    .player-shell .player-fallback {\n"
        "      width: 100%;\n"
        "      height: 100%;\n"
        "      border: 0;\n"
        "      display: block;\n"
        "    }\n"
        "    .player-fallback {\n"
        "      display: grid;\n"
        "      align-content: center;\n"
        "      gap: 14px;\n"
        "      padding: 20px;\n"
        "      color: #f4eadc;\n"
        "      background: linear-gradient(180deg, rgba(8, 10, 14, 0.92), rgba(20, 24, 30, 0.96));\n"
        "    }\n"
        "    .player-fallback p {\n"
        "      margin: 0;\n"
        "      font-size: 0.95rem;\n"
        "      line-height: 1.6;\n"
        "    }\n"
        "    .player-actions {\n"
        "      display: flex;\n"
        "      flex-wrap: wrap;\n"
        "      gap: 10px;\n"
        "    }\n"
        "    .player-link {\n"
        "      display: inline-flex;\n"
        "      align-items: center;\n"
        "      justify-content: center;\n"
        "      min-height: 42px;\n"
        "      padding: 0 14px;\n"
        "      border-radius: 999px;\n"
        "      background: rgba(255, 255, 255, 0.12);\n"
        "      color: #fff7ec;\n"
        "      text-decoration: none;\n"
        "      border: 1px solid rgba(255, 255, 255, 0.18);\n"
        "    }\n"
        "    .player-link:hover {\n"
        "      border-color: rgba(255, 255, 255, 0.32);\n"
        "    }\n"
        "    .control-row {\n"
        "      display: flex;\n"
        "      justify-content: space-between;\n"
        "      align-items: center;\n"
        "      gap: 16px;\n"
        "      color: var(--muted);\n"
        "      font-size: 0.95rem;\n"
        "    }\n"
        "    .runtime-warning {\n"
        "      display: none;\n"
        "      margin: 0 0 14px;\n"
        "      padding: 12px 14px;\n"
        "      border-radius: 16px;\n"
        "      border: 1px solid rgba(197, 106, 45, 0.28);\n"
        "      background: rgba(255, 242, 226, 0.95);\n"
        "      color: #5c4531;\n"
        "      font-size: 0.92rem;\n"
        "      line-height: 1.6;\n"
        "    }\n"
        "    .runtime-warning.is-visible {\n"
        "      display: block;\n"
        "    }\n"
        "    .runtime-warning code {\n"
        "      font-family: \"Noto Sans Mono\", monospace;\n"
        "      font-size: 0.92em;\n"
        "    }\n"
        "    .follow-toggle {\n"
        "      display: inline-flex;\n"
        "      align-items: center;\n"
        "      gap: 8px;\n"
        "      font-weight: 600;\n"
        "      color: var(--ink);\n"
        "    }\n"
        "    .follow-toggle input { accent-color: var(--accent); }\n"
        "    .transcript-stack {\n"
        "      display: grid;\n"
        "      gap: 18px;\n"
        "    }\n"
        "    .takeaways,\n"
        "    .transcript-section {\n"
        "      border-radius: 24px;\n"
        "      padding: 24px;\n"
        "    }\n"
        "    .takeaways h2,\n"
        "    .section-title {\n"
        "      margin: 0 0 14px;\n"
        "      font-size: 1.15rem;\n"
        "      letter-spacing: 0.02em;\n"
        "    }\n"
        "    .takeaways ul {\n"
        "      margin: 0;\n"
        "      padding-left: 20px;\n"
        "      display: grid;\n"
        "      gap: 8px;\n"
        "    }\n"
        "    .cue-list {\n"
        "      display: grid;\n"
        "      gap: 10px;\n"
        "    }\n"
        "    .cue {\n"
        "      padding: 14px 16px;\n"
        "      border-radius: 18px;\n"
        "      border: 1px solid transparent;\n"
        "      background: rgba(255, 250, 243, 0.7);\n"
        "      transition: background-color 160ms ease, border-color 160ms ease, transform 160ms ease;\n"
        "      cursor: pointer;\n"
        "    }\n"
        "    .cue:hover,\n"
        "    .cue:focus-visible {\n"
        "      border-color: rgba(197, 106, 45, 0.26);\n"
        "      outline: none;\n"
        "      transform: translateY(-1px);\n"
        "    }\n"
        "    .cue.is-active {\n"
        "      background: linear-gradient(135deg, rgba(255, 239, 219, 0.96), rgba(255, 247, 238, 0.98));\n"
        "      border-color: rgba(197, 106, 45, 0.48);\n"
        "      box-shadow: 0 10px 24px rgba(197, 106, 45, 0.14);\n"
        "    }\n"
        "    ruby {\n"
        "      display: inline-block;\n"
        "      ruby-position: under;\n"
      "      font-size: 1.02rem;\n"
        "    }\n"
        "    rt {\n"
        "      display: block;\n"
        "      font-size: 0.4em;\n"
        "      letter-spacing: 0.08em;\n"
        "      text-transform: uppercase;\n"
        "      color: var(--muted);\n"
        "      margin-top: 6px;\n"
        "    }\n"
        "    .dict-word {\n"
        "      display: inline;\n"
        "      color: inherit;\n"
        "      border-bottom: 1px dotted rgba(197, 106, 45, 0.45);\n"
        "      cursor: help;\n"
        "    }\n"
        "    .dict-word:hover {\n"
        "      color: var(--accent);\n"
        "      border-bottom-color: var(--accent);\n"
        "    }\n"
        "    .dictionary-popup {\n"
        "      position: fixed;\n"
        "      z-index: 1000;\n"
        "      width: min(320px, calc(100vw - 24px));\n"
        "      border-radius: 20px;\n"
        "      padding: 16px;\n"
        "      display: none;\n"
        "    }\n"
        "    .dictionary-popup.is-visible { display: block; }\n"
        "    .dictionary-popup-header {\n"
        "      display: flex;\n"
        "      justify-content: space-between;\n"
        "      align-items: start;\n"
        "      gap: 12px;\n"
        "      margin-bottom: 8px;\n"
        "    }\n"
        "    .dictionary-popup h3 {\n"
        "      margin: 0;\n"
        "      font-size: 1rem;\n"
        "    }\n"
        "    .dictionary-popup button {\n"
        "      appearance: none;\n"
        "      border: 0;\n"
        "      background: transparent;\n"
        "      color: var(--muted);\n"
        "      font-size: 1rem;\n"
        "      cursor: pointer;\n"
        "    }\n"
        "    .dictionary-popup p { margin: 0.35rem 0; }\n"
        "    .status-message {\n"
        "      color: var(--muted);\n"
        "      font-size: 0.92rem;\n"
        "      margin: 12px 0 0;\n"
        "    }\n"
        "    @media (max-width: 980px) {\n"
        "      .layout { grid-template-columns: 1fr; }\n"
        "      .panel { position: static; }\n"
        "    }\n"
        "  </style>\n"
        "</head>\n"
        "<body>\n"
        "  <div class=\"shell\">\n"
        "    <header class=\"hero\">\n"
        "      <p class=\"eyebrow\">Shadowing Study Page</p>\n"
        f"      <h1>{safe_title}</h1>\n"
        "      <div class=\"meta\">\n"
        f"        <span>Source video: <a href=\"{safe_url}\">{escaped_url_text}</a></span>\n"
        "        <span>Click a subtitle line to seek the video</span>\n"
        "        <span>Select or click an English word for a quick definition</span>\n"
        "      </div>\n"
        "    </header>\n"
        "    <div class=\"layout\">\n"
        "      <aside class=\"panel\">\n"
        "        <div class=\"player-shell\"><div id=\"player\"></div></div>\n"
        "        <div class=\"runtime-warning\" id=\"runtime-warning\" hidden></div>\n"
        "        <div class=\"control-row\">\n"
          "          <div id=\"sync-status\">Loading synchronized playback...</div>\n"
        "          <label class=\"follow-toggle\"><input id=\"auto-follow\" type=\"checkbox\" checked>Auto-follow</label>\n"
        "        </div>\n"
        "        <p class=\"status-message\">If playback synchronization is unavailable, the transcript remains readable and cue click-to-seek will fall back to opening the video on YouTube at the selected timestamp.</p>\n"
        "      </aside>\n"
        "      <main class=\"transcript-stack\" id=\"transcript-root\">\n"
        f"        {takeaways_html}\n"
        f"        {sections_html}\n"
        "      </main>\n"
        "    </div>\n"
        "  </div>\n"
        "  <div class=\"dictionary-popup\" id=\"dictionary-popup\" role=\"dialog\" aria-live=\"polite\" aria-modal=\"false\">\n"
        "    <div class=\"dictionary-popup-header\">\n"
        "      <h3 id=\"dictionary-word\">Dictionary</h3>\n"
        "      <button type=\"button\" id=\"dictionary-close\" aria-label=\"Close definition\">Close</button>\n"
        "    </div>\n"
        "    <div id=\"dictionary-body\"><p>Select or click an English word to see its definition.</p></div>\n"
        "  </div>\n"
        "  <script>\n"
        f"    const VIDEO_ID = {video_id!r};\n"
        f"    const SOURCE_VIDEO_URL = {youtube_url!r};\n"
        "    const cues = Array.from(document.querySelectorAll('.cue[data-start][data-end]')).map(function (element, index) {\n"
        "      return {\n"
        "        element: element,\n"
        "        index: index,\n"
        "        start: Number(element.dataset.start),\n"
        "        end: Number(element.dataset.end)\n"
        "      };\n"
        "    }).sort(function (a, b) { return a.start - b.start; });\n"
        "    const syncStatus = document.getElementById('sync-status');\n"
        "    const autoFollow = document.getElementById('auto-follow');\n"
        "    const runtimeWarning = document.getElementById('runtime-warning');\n"
        "    const popup = document.getElementById('dictionary-popup');\n"
        "    const popupWord = document.getElementById('dictionary-word');\n"
        "    const popupBody = document.getElementById('dictionary-body');\n"
        "    const definitionCache = new Map();\n"
        "    let player = null;\n"
        "    let activeCueIndex = -1;\n"
        "    let pollHandle = null;\n"
        "    let youtubeReady = false;\n"
        "    const IS_FILE_PROTOCOL = window.location.protocol === 'file:';\n"
        "    const PAGE_ORIGIN = (!IS_FILE_PROTOCOL && window.location.origin && window.location.origin !== 'null') ? window.location.origin : '';\n"
        "    const PAGE_HREF = !IS_FILE_PROTOCOL ? window.location.href : '';\n"
        "    const fallbackTimer = window.setTimeout(showFallbackPlayer, 5000);\n"
        "\n"
        "    function setStatus(message) {\n"
        "      syncStatus.textContent = message;\n"
        "    }\n"
        "\n"
        "    function buildEmbedUrl(enableJsApi) {\n"
        "      const params = new URLSearchParams();\n"
        "      params.set('playsinline', '1');\n"
        "      params.set('rel', '0');\n"
        "      if (enableJsApi) {\n"
        "        params.set('enablejsapi', '1');\n"
        "      }\n"
        "      if (PAGE_ORIGIN) {\n"
        "        params.set('origin', PAGE_ORIGIN);\n"
        "      }\n"
        "      if (PAGE_HREF) {\n"
        "        params.set('widget_referrer', PAGE_HREF);\n"
        "      }\n"
        "      return 'https://www.youtube.com/embed/' + encodeURIComponent(VIDEO_ID) + '?' + params.toString();\n"
        "    }\n"
        "\n"
        "    function buildTimestampedWatchUrl(seconds) {\n"
        "      const target = new URL(SOURCE_VIDEO_URL);\n"
        "      target.searchParams.set('t', String(Math.max(0, Math.floor(seconds))));\n"
        "      return target.toString();\n"
        "    }\n"
        "\n"
        "    function showRuntimeWarning(message) {\n"
        "      runtimeWarning.hidden = false;\n"
        "      runtimeWarning.classList.add('is-visible');\n"
        "      runtimeWarning.innerHTML = message;\n"
        "    }\n"
        "\n"
        "    function showFileModeGuidance() {\n"
        "      showRuntimeWarning(\n"
        "        'This page is opened as a local <code>file://</code>. YouTube blocks embedded playback in that context because the request has no HTTP referrer, which triggers error 153. Serve this file over <code>http://127.0.0.1</code> or another HTTP(S) origin to restore synchronized playback. Example: <code>python3 -m http.server 8000</code> then open this page through localhost.'\n"
        "      );\n"
        "    }\n"
        "\n"
        "    function renderPlayerFallback(message) {\n"
        "      const container = document.getElementById('player');\n"
        "      container.innerHTML = '';\n"
        "      const panel = document.createElement('div');\n"
        "      panel.className = 'player-fallback';\n"
        "      panel.innerHTML = '<p>' + message + '</p>' +\n"
        "        '<div class=\"player-actions\">' +\n"
        "        '<a class=\"player-link\" href=\"' + SOURCE_VIDEO_URL + '\" target=\"_blank\" rel=\"noopener\">Open on YouTube</a>' +\n"
        "        '</div>';\n"
        "      container.appendChild(panel);\n"
        "    }\n"
        "\n"
        "    function findCueIndex(currentTime) {\n"
        "      let low = 0;\n"
        "      let high = cues.length - 1;\n"
        "      let candidate = -1;\n"
        "      while (low <= high) {\n"
        "        const mid = Math.floor((low + high) / 2);\n"
        "        if (cues[mid].start <= currentTime) {\n"
        "          candidate = mid;\n"
        "          low = mid + 1;\n"
        "        } else {\n"
        "          high = mid - 1;\n"
        "        }\n"
        "      }\n"
        "      if (candidate === -1) {\n"
        "        return -1;\n"
        "      }\n"
        "      const cue = cues[candidate];\n"
        "      if (currentTime <= cue.end + 0.08) {\n"
        "        return candidate;\n"
        "      }\n"
        "      return -1;\n"
        "    }\n"
        "\n"
        "    function updateActiveCue(index) {\n"
        "      if (index === activeCueIndex) {\n"
        "        return;\n"
        "      }\n"
        "      if (activeCueIndex >= 0 && cues[activeCueIndex]) {\n"
        "        cues[activeCueIndex].element.classList.remove('is-active');\n"
        "      }\n"
        "      activeCueIndex = index;\n"
        "      if (index >= 0 && cues[index]) {\n"
        "        cues[index].element.classList.add('is-active');\n"
        "        if (autoFollow.checked) {\n"
        "          cues[index].element.scrollIntoView({ block: 'nearest', behavior: 'smooth' });\n"
        "        }\n"
        "      }\n"
        "    }\n"
        "\n"
        "    function syncFromPlayer() {\n"
        "      if (!player || typeof player.getCurrentTime !== 'function') {\n"
        "        return;\n"
        "      }\n"
        "      updateActiveCue(findCueIndex(player.getCurrentTime()));\n"
        "    }\n"
        "\n"
        "    function startPolling() {\n"
        "      if (pollHandle !== null) {\n"
        "        return;\n"
        "      }\n"
        "      pollHandle = window.setInterval(syncFromPlayer, 120);\n"
        "    }\n"
        "\n"
        "    function showFallbackPlayer() {\n"
        "      if (youtubeReady) {\n"
        "        return;\n"
        "      }\n"
        "      if (IS_FILE_PROTOCOL) {\n"
        "        showFileModeGuidance();\n"
        "        renderPlayerFallback('Embedded playback is disabled in local file mode. Use the localhost preview guidance above, or open the source video on YouTube.');\n"
        "        setStatus('Embedded playback is unavailable in file mode. Cue clicks will open YouTube at the matching timestamp.');\n"
        "        return;\n"
        "      }\n"
        "      const container = document.getElementById('player');\n"
        "      container.innerHTML = '';\n"
        "      const iframe = document.createElement('iframe');\n"
        "      iframe.src = buildEmbedUrl(false);\n"
        "      iframe.title = 'YouTube video player';\n"
        "      iframe.allow = 'accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share';\n"
        "      iframe.allowFullscreen = true;\n"
        "      container.appendChild(iframe);\n"
        "      setStatus('Playback loaded, but automatic synchronization is unavailable because the YouTube API did not initialize. Cue clicks will still seek via YouTube links if needed.');\n"
        "    }\n"
        "\n"
        "    function seekToCue(cue) {\n"
        "      if (!cue) {\n"
        "        return;\n"
        "      }\n"
        "      updateActiveCue(cue.index);\n"
        "      if (!player || typeof player.seekTo !== 'function') {\n"
        "        window.open(buildTimestampedWatchUrl(cue.start), '_blank', 'noopener');\n"
        "        return;\n"
        "      }\n"
        "      player.seekTo(Math.max(cue.start, 0), true);\n"
        "      if (typeof player.playVideo === 'function') {\n"
        "        player.playVideo();\n"
        "      }\n"
        "    }\n"
        "\n"
        "    cues.forEach(function (cue) {\n"
        "      cue.element.addEventListener('click', function () { seekToCue(cue); });\n"
        "      cue.element.addEventListener('keydown', function (event) {\n"
        "        if (event.key === 'Enter' || event.key === ' ') {\n"
        "          event.preventDefault();\n"
        "          seekToCue(cue);\n"
        "        }\n"
        "      });\n"
        "    });\n"
        "\n"
        "    function showPopupAt(rect) {\n"
        "      const maxLeft = window.innerWidth - popup.offsetWidth - 12;\n"
        "      const left = Math.max(12, Math.min(rect.left, maxLeft));\n"
        "      const top = Math.max(12, rect.bottom + 12);\n"
        "      popup.style.left = left + 'px';\n"
        "      popup.style.top = Math.min(top, window.innerHeight - popup.offsetHeight - 12) + 'px';\n"
        "      popup.classList.add('is-visible');\n"
        "    }\n"
        "\n"
        "    function renderDefinition(word, result) {\n"
        "      popupWord.textContent = word;\n"
        "      popupBody.innerHTML = result;\n"
        "    }\n"
        "\n"
        "    function summarizeEntry(entry) {\n"
        "      const meanings = Array.isArray(entry.meanings) ? entry.meanings : [];\n"
        "      const firstMeaning = meanings[0] || {};\n"
        "      const partOfSpeech = firstMeaning.partOfSpeech ? '<p><strong>' + firstMeaning.partOfSpeech + '</strong></p>' : '';\n"
        "      const definitions = Array.isArray(firstMeaning.definitions) ? firstMeaning.definitions : [];\n"
        "      const firstDefinition = definitions[0] || {};\n"
        "      const definitionText = firstDefinition.definition ? '<p>' + firstDefinition.definition + '</p>' : '<p>Definition unavailable.</p>';\n"
        "      const exampleText = firstDefinition.example ? '<p><em>Example: ' + firstDefinition.example + '</em></p>' : '';\n"
        "      return partOfSpeech + definitionText + exampleText;\n"
        "    }\n"
        "\n"
        "    async function lookupWord(word, rect) {\n"
        "      const normalized = word.toLowerCase();\n"
        "      popupWord.textContent = normalized;\n"
        "      popupBody.innerHTML = '<p>Loading definition...</p>';\n"
        "      popup.classList.add('is-visible');\n"
        "      showPopupAt(rect);\n"
        "      if (!definitionCache.has(normalized)) {\n"
        "        const request = fetch('https://api.dictionaryapi.dev/api/v2/entries/en/' + encodeURIComponent(normalized))\n"
        "          .then(function (response) {\n"
        "            if (!response.ok) {\n"
        "              throw new Error('Dictionary service unavailable');\n"
        "            }\n"
        "            return response.json();\n"
        "          })\n"
        "          .then(function (payload) {\n"
        "            if (!Array.isArray(payload) || !payload.length) {\n"
        "              return '<p>No dictionary entry was available for this word.</p>';\n"
        "            }\n"
        "            return summarizeEntry(payload[0]);\n"
        "          })\n"
        "          .catch(function () {\n"
        "            return '<p>Definition unavailable right now. Please try again later.</p>';\n"
        "          });\n"
        "        definitionCache.set(normalized, request);\n"
        "      }\n"
        "      const htmlResult = await definitionCache.get(normalized);\n"
        "      renderDefinition(normalized, htmlResult);\n"
        "      showPopupAt(rect);\n"
        "    }\n"
        "\n"
        "    document.getElementById('transcript-root').addEventListener('click', function (event) {\n"
        "      const word = event.target.closest('.dict-word');\n"
        "      if (!word) {\n"
        "        return;\n"
        "      }\n"
        "      lookupWord(word.dataset.word, word.getBoundingClientRect());\n"
        "    });\n"
        "\n"
        "    document.getElementById('transcript-root').addEventListener('mouseup', function () {\n"
        "      const selection = window.getSelection();\n"
        "      if (!selection || selection.isCollapsed || !selection.rangeCount) {\n"
        "        return;\n"
        "      }\n"
        "      const text = selection.toString().trim();\n"
        "      if (!/^[A-Za-z]+(?:['-][A-Za-z]+)*$/.test(text)) {\n"
        "        return;\n"
        "      }\n"
        "      const rect = selection.getRangeAt(0).getBoundingClientRect();\n"
        "      lookupWord(text, rect);\n"
        "    });\n"
        "\n"
        "    document.getElementById('dictionary-close').addEventListener('click', function () {\n"
        "      popup.classList.remove('is-visible');\n"
        "    });\n"
        "\n"
        "    document.addEventListener('click', function (event) {\n"
        "      if (!popup.contains(event.target) && !event.target.closest('.dict-word')) {\n"
        "        popup.classList.remove('is-visible');\n"
        "      }\n"
        "    });\n"
        "\n"
        "    document.addEventListener('keydown', function (event) {\n"
        "      if (event.key === 'Escape') {\n"
        "        popup.classList.remove('is-visible');\n"
        "      }\n"
        "    });\n"
        "\n"
        "    window.onYouTubeIframeAPIReady = function () {\n"
        "      if (IS_FILE_PROTOCOL) {\n"
        "        showFallbackPlayer();\n"
        "        return;\n"
        "      }\n"
        "      youtubeReady = true;\n"
        "      window.clearTimeout(fallbackTimer);\n"
        "      player = new window.YT.Player('player', {\n"
        "        videoId: VIDEO_ID,\n"
        "        playerVars: {\n"
        "          playsinline: 1,\n"
        "          rel: 0,\n"
        "          origin: PAGE_ORIGIN,\n"
        "          widget_referrer: PAGE_HREF\n"
        "        },\n"
        "        events: {\n"
        "          onReady: function () {\n"
            "            setStatus('Playback synchronized. Active subtitle highlighting is ready.');\n"
        "            startPolling();\n"
        "            syncFromPlayer();\n"
        "          },\n"
        "          onStateChange: function () {\n"
        "            startPolling();\n"
        "            syncFromPlayer();\n"
        "          },\n"
        "          onError: function (event) {\n"
        "            if (event && event.data === 153) {\n"
        "              showFileModeGuidance();\n"
        "              showFallbackPlayer();\n"
        "              setStatus('YouTube blocked embedded playback because the page was missing an HTTP referrer or equivalent client identity.');\n"
        "              return;\n"
        "            }\n"
        "            setStatus('Playback failed to synchronize. The transcript remains fully readable.');\n"
          "          }\n"
        "        }\n"
        "      });\n"
        "    };\n"
        "\n"
        "    if (IS_FILE_PROTOCOL) {\n"
        "      showFallbackPlayer();\n"
        "    } else {\n"
        "      const apiScript = document.createElement('script');\n"
        "      apiScript.src = 'https://www.youtube.com/iframe_api';\n"
        "      apiScript.async = true;\n"
        "      apiScript.onerror = showFallbackPlayer;\n"
        "      document.head.appendChild(apiScript);\n"
        "    }\n"
        "  </script>\n"
        "</body>\n"
        "</html>\n"
    )


def main() -> int:
    args = parse_args()
    input_path = Path(args.input_html)
    title, cues, takeaways = parse_input_html(input_path)
    if args.title:
        title = args.title
    video_id = extract_youtube_id(args.youtube_url)
    output_path = Path(args.output) if args.output else Path(sanitize_filename(title))
    html_content = build_html(title, args.youtube_url, video_id, cues, takeaways)
    output_path.write_text(html_content, encoding="utf-8")
    print(f"Wrote optimized shadowing HTML to {output_path}")
    print(f"Cues: {len(cues)}")
    print(f"Takeaways: {len(takeaways)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
