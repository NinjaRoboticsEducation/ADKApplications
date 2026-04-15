"""Deterministic HTML skeleton rendering for yttranscript_app."""

from __future__ import annotations

import html
from dataclasses import dataclass

from .transcript_structure import StructuredDocument, TranscriptCue


@dataclass(frozen=True)
class BaseHtmlRender:
    """Rendered deterministic HTML plus a title chosen for the document."""

    title: str
    html_content: str


def _timestamp_to_seconds(value: str) -> float:
    hours, minutes, seconds = value.split(":")
    return int(hours) * 3600 + int(minutes) * 60 + float(seconds)


def _render_cue(cue: TranscriptCue) -> str:
    time_label = f"[{cue.start_raw} --> {cue.end_raw}]"
    return (
        f'<div class="cue" data-start="{_timestamp_to_seconds(cue.start_raw):.3f}" '
        f'data-end="{_timestamp_to_seconds(cue.end_raw):.3f}">'
        f'<span class="cue-time">{html.escape(time_label)}</span> '
        f'<span class="cue-text">{html.escape(cue.text)}</span>'
        "</div>"
    )


def render_base_html(
    *,
    title: str,
    source_url: str,
    document: StructuredDocument,
) -> BaseHtmlRender:
    """Render a stable intermediate HTML document for the shadowing optimizer."""
    safe_title = html.escape(title)
    safe_url = html.escape(source_url, quote=True)
    safe_url_text = html.escape(source_url)

    bullets = "".join(f"<li>{html.escape(item)}</li>" for item in document.takeaways)
    takeaways_html = (
        '<section class="takeaways">'
        "<h2>Key Takeaways</h2>"
        f"<ul>{bullets}</ul>"
        "</section>"
    )

    section_html = []
    for index, section in enumerate(document.sections, start=1):
        cues_html = "".join(_render_cue(cue) for cue in section.cues)
        section_html.append(
            '<section class="transcript-section">'
            f'<h2 class="section-title">Section {index}: {html.escape(section.title)}</h2>'
            f"{cues_html}"
            "</section>"
        )

    page = (
        "<!doctype html>\n"
        '<html lang="en">\n'
        "<head>\n"
        '  <meta charset="utf-8">\n'
        '  <meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f"  <title>{safe_title}</title>\n"
        "  <style>\n"
        "    body { font-family: 'Noto Sans', 'Noto Sans JP', sans-serif; margin: 0 auto; max-width: 980px; padding: 32px 20px 48px; line-height: 1.7; color: #1d1c19; background: #f7f4ee; }\n"
        "    a { color: #a7531d; }\n"
        "    .hero, .takeaways, .transcript-section { background: #fffdf9; border: 1px solid rgba(30,29,25,0.08); border-radius: 22px; padding: 22px; box-shadow: 0 10px 30px rgba(40,30,20,0.08); }\n"
        "    .hero { margin-bottom: 18px; }\n"
        "    .takeaways, .transcript-section { margin-top: 18px; }\n"
        "    .cue { display: block; padding: 10px 0; border-top: 1px solid rgba(30,29,25,0.08); }\n"
        "    .cue:first-child { border-top: 0; }\n"
        "    .cue-time { display: inline-block; min-width: 18ch; color: #6c6559; font-family: 'Noto Sans Mono', monospace; }\n"
        "    .cue-text { display: inline; }\n"
        "  </style>\n"
        "</head>\n"
        "<body>\n"
        '  <header class="hero">\n'
        "    <p>Shadowing Study Material</p>\n"
        f"    <h1>{safe_title}</h1>\n"
        f'    <p>Source video: <a href="{safe_url}">{safe_url_text}</a></p>\n'
        "  </header>\n"
        f"  {takeaways_html}\n"
        f"  {''.join(section_html)}\n"
        "</body>\n"
        "</html>\n"
    )
    return BaseHtmlRender(title=title, html_content=page)
