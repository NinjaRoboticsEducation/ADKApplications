"""
Safe Markdown-to-HTML conversion for learner-facing Japanese transcripts.
"""

from __future__ import annotations

import html
import pathlib
import re
from collections import defaultdict
from dataclasses import dataclass, field

from .furigana_tools import extract_furigana_spans
from .text_processing import RAW_TIMESTAMP_LINE_PATTERN


INLINE_TIMESTAMP_PATTERN = re.compile(r"(?<!\d)(\d{1,2}:\d{2}(?::\d{2})?)(?!\d)")
FURIGANA_TEXT_PATTERN = re.compile(r"([^\s（）()]+)（[ぁ-んァ-ヶー]+）")
DIALOGUE_PATTERN = re.compile(r"^(?:\*\*)?(.{1,40}?)(?:\*\*)?\s*[：:]\s*(.+)$", re.DOTALL)
SUMMARY_MAX_LENGTH = 118


@dataclass
class RenderContext:
    footnote_counts: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    first_footnote_ids: dict[str, str] = field(default_factory=dict)


@dataclass
class ContentBlock:
    kind: str
    text: str = ""
    items: list[str] = field(default_factory=list)


@dataclass
class BodySection:
    anchor: str
    heading: str
    blocks: list[ContentBlock] = field(default_factory=list)


@dataclass
class BodyDocument:
    title: str
    sections: list[BodySection]
    explicit_toc: list[str] = field(default_factory=list)
    has_ruby: bool = False
    has_timestamps: bool = False


def convert_to_html(markdown_text: str) -> str:
    """Convert transcript markdown into a complete HTML5 document."""
    parts = re.split(r"\n---\s*\n", markdown_text, maxsplit=1)
    body_md = parts[0].strip()
    glossary_md = parts[1].strip() if len(parts) > 1 else ""

    context = RenderContext()
    title = _derive_title(body_md)
    document = _parse_body_document(body_md, title=title)
    glossary_html = (
        _convert_glossary(glossary_md, context=context) if glossary_md else ""
    )
    page_html = _render_page(document, glossary_html=glossary_html, context=context)
    return _wrap_in_html(title, page_html)


def _derive_title(body_md: str) -> str:
    h1_match = re.search(r"(?m)^#\s+(.+)$", body_md)
    if h1_match:
        title = h1_match.group(1).strip()
    else:
        h2_match = re.search(r"(?m)^##\s+(.+)$", body_md)
        title = h2_match.group(1).strip() if h2_match else "JP Transcript"
    title = _clean_heading_text(title)
    return title or "JP Transcript"


def _clean_heading_text(text: str) -> str:
    cleaned = re.sub(r"（[ぁ-んァ-ヶー]+）", "", text)
    cleaned = re.sub(r"\*(\d+)", "", cleaned)
    cleaned = cleaned.replace("【用語】", "")
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip(" -:：。．") or "JP Transcript"


def _strip_markdown_emphasis(text: str) -> str:
    match = re.fullmatch(r"\*\*(.+?)\*\*", text.strip())
    if match:
        return match.group(1).strip()
    return text.strip()


def _plain_text(text: str) -> str:
    normalized = FURIGANA_TEXT_PATTERN.sub(r"\1", text)
    normalized = re.sub(r"`(.+?)`", r"\1", normalized)
    normalized = re.sub(r"\*\*(.+?)\*\*", r"\1", normalized)
    normalized = re.sub(r"\*(\d+)", "", normalized)
    normalized = re.sub(r"^#{1,6}\s+", "", normalized)
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized.strip()


def _trim_summary(text: str, *, max_length: int = SUMMARY_MAX_LENGTH) -> str:
    if len(text) <= max_length:
        return text

    for punctuation in "。！？.!?":
        boundary = text.rfind(punctuation, 0, max_length)
        if boundary >= max_length // 2:
            return text[: boundary + 1].strip()
    return text[:max_length].rstrip(" 、,") + "…"


def _looks_like_dialogue_speaker(label: str) -> bool:
    normalized = _plain_text(label)
    if not normalized or len(normalized) > 20:
        return False
    if any(token in normalized for token in ["。", "！", "？", ".", "!", "?"]):
        return False
    return bool(re.fullmatch(r"[\w一-龯々ぁ-んァ-ヶー・（）() 　]+", normalized))


def _split_dialogue(text: str) -> tuple[str, str] | None:
    match = DIALOGUE_PATTERN.match(text.strip())
    if not match:
        return None

    speaker = _strip_markdown_emphasis(match.group(1))
    dialogue = match.group(2).strip()
    if not dialogue or not _looks_like_dialogue_speaker(speaker):
        return None
    return speaker, dialogue


def _parse_body_document(md: str, *, title: str) -> BodyDocument:
    lines = md.splitlines()
    explicit_toc: list[str] = []
    sections: list[BodySection] = []
    intro_blocks: list[ContentBlock] = []
    current_heading: str | None = None
    current_blocks: list[ContentBlock] = []
    paragraph_buffer: list[str] = []
    list_buffer: list[str] = []

    def active_blocks() -> list[ContentBlock]:
        return current_blocks if current_heading is not None else intro_blocks

    def flush_paragraph() -> None:
        nonlocal paragraph_buffer
        if paragraph_buffer:
            joined = " ".join(part.strip() for part in paragraph_buffer if part.strip())
            if joined:
                active_blocks().append(ContentBlock(kind="paragraph", text=joined))
            paragraph_buffer = []

    def flush_list() -> None:
        nonlocal list_buffer
        if list_buffer:
            active_blocks().append(ContentBlock(kind="list", items=list(list_buffer)))
            list_buffer = []

    def flush_buffers() -> None:
        flush_paragraph()
        flush_list()

    def push_section(heading: str, blocks: list[ContentBlock]) -> None:
        if not blocks:
            return
        anchor = f"section-{len(sections) + 1}"
        sections.append(BodySection(anchor=anchor, heading=heading, blocks=list(blocks)))

    index = 0
    while index < len(lines):
        stripped = lines[index].strip()

        if not stripped:
            flush_buffers()
            index += 1
            continue

        if stripped == "**目次**":
            flush_buffers()
            index += 1
            while index < len(lines):
                current = lines[index].strip()
                if not current:
                    index += 1
                    continue
                bullet = re.match(r"^[-*]\s+(.+)$", current)
                if not bullet:
                    break
                explicit_toc.append(_clean_heading_text(bullet.group(1)))
                index += 1
            continue

        if RAW_TIMESTAMP_LINE_PATTERN.fullmatch(stripped):
            flush_buffers()
            active_blocks().append(ContentBlock(kind="timestamp", text=stripped))
            index += 1
            continue

        heading_match = re.match(r"^(#{1,6})\s+(.+)$", stripped)
        if heading_match:
            flush_buffers()
            level = len(heading_match.group(1))
            raw_heading = re.sub(r"\*(\d+)", "", heading_match.group(2)).strip()

            if level == 1:
                index += 1
                continue

            if current_heading is None and intro_blocks:
                push_section("イントロダクション", intro_blocks)
                intro_blocks = []
            elif current_heading is not None:
                push_section(current_heading, current_blocks)
                current_blocks = []

            current_heading = raw_heading
            index += 1
            continue

        bullet_match = re.match(r"^[-*]\s+(.+)$", stripped)
        if bullet_match:
            flush_paragraph()
            list_buffer.append(bullet_match.group(1).strip())
            index += 1
            continue

        paragraph_buffer.append(stripped)
        index += 1

    flush_buffers()

    if current_heading is not None:
        push_section(current_heading, current_blocks)
    elif intro_blocks:
        push_section("本文", intro_blocks)

    if not sections:
        sections.append(
            BodySection(
                anchor="section-1",
                heading="本文",
                blocks=[ContentBlock(kind="paragraph", text=title)],
            )
        )

    return BodyDocument(
        title=title,
        sections=sections,
        explicit_toc=explicit_toc,
        has_ruby=bool(FURIGANA_TEXT_PATTERN.search(md)),
        has_timestamps=bool(
            RAW_TIMESTAMP_LINE_PATTERN.search(md) or INLINE_TIMESTAMP_PATTERN.search(md)
        ),
    )


def _derive_lede(document: BodyDocument) -> str:
    fragments: list[str] = []
    for section in document.sections:
        for block in section.blocks:
            if block.kind != "paragraph":
                continue
            dialogue = _split_dialogue(block.text)
            summary_source = dialogue[1] if dialogue else block.text
            summary = _plain_text(summary_source)
            if summary:
                fragments.append(summary)
            if len(" ".join(fragments)) >= SUMMARY_MAX_LENGTH:
                break
        if len(" ".join(fragments)) >= SUMMARY_MAX_LENGTH:
            break

    if not fragments:
        return "日本語の長文コンテンツを、ふりがなと用語解説つきで読みやすく整理した学習用トランスクリプトです。"

    return _trim_summary(" ".join(fragments))


def _derive_meta_chips(document: BodyDocument, *, glossary_present: bool) -> list[str]:
    chips = [f"{len(document.sections)} Sections"]
    if document.has_ruby:
        chips.append("Ruby Support")
    if glossary_present:
        chips.append("Glossary Linked")
    if document.has_timestamps:
        chips.append("Timestamps Included")
    if len(chips) == 1:
        chips.append("Learner Friendly")
    return chips


def _render_page(
    document: BodyDocument,
    *,
    glossary_html: str,
    context: RenderContext,
) -> str:
    lede = _derive_lede(document)
    chips = _derive_meta_chips(document, glossary_present=bool(glossary_html))

    page_parts = [
        "  <main>",
        '    <header class="hero">',
        '      <p class="eyebrow">Japanese Podcast Transcript</p>',
        f"      <h1>{html.escape(document.title, quote=True)}</h1>",
        f"      <p class=\"lede\">{html.escape(lede, quote=True)}</p>",
        '      <div class="meta">',
    ]

    for chip in chips:
        page_parts.append(f'        <span class="chip">{html.escape(chip, quote=True)}</span>')

    page_parts.extend(
        [
            "      </div>",
            "    </header>",
            '    <div class="layout">',
            _render_toc(document, context=context),
            "      <article>",
        ]
    )

    for section in document.sections:
        page_parts.append(_render_section(section, context=context))

    if glossary_html:
        page_parts.append(glossary_html)

    page_parts.extend(["      </article>", "    </div>", "  </main>"])
    return "\n".join(page_parts)


def _render_toc(document: BodyDocument, *, context: RenderContext) -> str:
    toc_parts = [
        '      <aside class="toc">',
        '        <p class="toc-title"><ruby>目次<rt>もくじ</rt></ruby></p>',
        '        <nav aria-label="目次">',
        "          <ul>",
    ]

    for section in document.sections:
        label_html = _convert_inline(
            section.heading,
            context=context,
            allow_footnotes=False,
        )
        toc_parts.append(
            f'            <li><a href="#{section.anchor}">{label_html}</a></li>'
        )

    toc_parts.extend(["          </ul>", "        </nav>", "      </aside>"])
    return "\n".join(toc_parts)


def _render_section(section: BodySection, *, context: RenderContext) -> str:
    section_parts = [
        f'        <section id="{section.anchor}" class="content-section">',
        f"          <h2>{_convert_inline(section.heading, context=context, allow_footnotes=False)}</h2>",
    ]

    for block in section.blocks:
        if block.kind == "paragraph":
            dialogue = _split_dialogue(block.text)
            if dialogue:
                speaker_html = _convert_inline(
                    dialogue[0],
                    context=context,
                    allow_footnotes=False,
                )
                text_html = _convert_inline(dialogue[1], context=context)
                section_parts.append(
                    "          "
                    f'<p class="dialogue"><strong class="speaker">{speaker_html}</strong>'
                    f'<span class="dialogue-text">{text_html}</span></p>'
                )
            else:
                text_html = _convert_inline(block.text, context=context)
                section_parts.append(f"          <p>{text_html}</p>")
            continue

        if block.kind == "list":
            section_parts.append("          <ul>")
            for item in block.items:
                item_html = _convert_inline(item, context=context)
                section_parts.append(f"            <li>{item_html}</li>")
            section_parts.append("          </ul>")
            continue

        if block.kind == "timestamp":
            section_parts.append(
                f'          <p class="timestamp">{_render_time(block.text)}</p>'
            )

    section_parts.append("        </section>")
    return "\n".join(section_parts)


def _convert_glossary(md: str, *, context: RenderContext) -> str:
    heading_match = re.search(r"^#{1,6}\s+(.+)$", md, re.MULTILINE)
    heading_text = heading_match.group(1).strip() if heading_match else "言葉の解説"

    entries = []
    for chunk in re.split(r"(?m)^(?=\d+\.\s+)", md):
        block = chunk.strip()
        if not block or not re.match(r"^\d+\.\s+", block):
            continue
        entries.append(block)

    html_parts = [
        '        <section id="glossary" class="content-section glossary-section">',
        f"          <h3>{html.escape(heading_text, quote=True)}</h3>",
        '          <ol class="glossary-list">',
    ]

    for entry in entries:
        entry_match = re.match(r"^(\d+)\.\s+(.+)$", entry, re.DOTALL)
        if not entry_match:
            continue

        number = entry_match.group(1)
        content = entry_match.group(2).strip()
        lines = [line.strip() for line in content.splitlines() if line.strip()]
        term = lines[0] if lines else ""
        backlink_id = context.first_footnote_ids.get(number, f"ref-{number}-1")

        html_parts.extend(
            [
                f'            <li id="glossary-{number}" class="glossary-entry">',
                '              <div class="glossary-head">',
                f'                <span class="glossary-number">{html.escape(number, quote=True)}</span>',
                f"                <h4>{_convert_inline(term, context=context, allow_footnotes=False)}</h4>",
                "              </div>",
            ]
        )

        current_block: dict[str, object] | None = None
        blocks: list[dict[str, object]] = []

        for line in lines[1:]:
            subitem = re.match(r"\*\s+\*\*(.+?)\*\*[:：]?\s*(.*)$", line)
            if subitem:
                current_block = {
                    "label": subitem.group(1).rstrip(":：").strip(),
                    "value": subitem.group(2).strip(),
                    "items": [],
                }
                blocks.append(current_block)
                continue

            nested = re.match(r"\*\s+(.*)$", line)
            if nested:
                if current_block is None:
                    current_block = {"label": "", "value": "", "items": []}
                    blocks.append(current_block)
                current_block.setdefault("items", []).append(nested.group(1).strip())

        for block in blocks:
            label = str(block.get("label", "")).strip()
            value = str(block.get("value", "")).strip()
            items = [str(item) for item in block.get("items", [])]

            label_html = html.escape(label, quote=True) if label else ""
            value_html = (
                _convert_inline(value, context=context, allow_footnotes=False)
                if value
                else ""
            )

            if items or _uses_glossary_card_block(label):
                html_parts.append('              <div class="glossary-block">')
                if label:
                    if value_html:
                        html_parts.append(
                            f"                <p><strong>{label_html}:</strong> {value_html}</p>"
                        )
                    else:
                        html_parts.append(f"                <p><strong>{label_html}:</strong></p>")
                elif value_html:
                    html_parts.append(f"                <p>{value_html}</p>")

                if items:
                    html_parts.append("                <ul>")
                    for item in items:
                        html_parts.append(
                            "                  "
                            f"<li>{_convert_inline(item, context=context, allow_footnotes=False)}</li>"
                        )
                    html_parts.append("                </ul>")

                html_parts.append("              </div>")
                continue

            if label:
                html_parts.append(
                    f"              <p><strong>{label_html}:</strong> {value_html}</p>"
                )
            elif value_html:
                html_parts.append(f"              <p>{value_html}</p>")

        html_parts.append(
            f'              <p><a href="#{backlink_id}" class="backlink">本文へ戻る</a></p>'
        )
        html_parts.append("            </li>")

    html_parts.extend(["          </ol>", "        </section>"])
    return "\n".join(html_parts)


def _uses_glossary_card_block(label: str) -> bool:
    if not label:
        return False
    return any(keyword in label for keyword in ["例文", "Examples", "比較", "Comparison"])


def _convert_inline(
    text: str,
    *,
    context: RenderContext,
    allow_footnotes: bool = True,
) -> str:
    output: list[str] = []
    cursor = 0
    for match in re.finditer(r"\*\*(.+?)\*\*", text):
        output.append(
            _convert_inline_plain(
                text[cursor:match.start()],
                context=context,
                allow_footnotes=allow_footnotes,
            )
        )
        strong_content = _convert_inline_plain(
            match.group(1),
            context=context,
            allow_footnotes=allow_footnotes,
        )
        output.append(f"<strong>{strong_content}</strong>")
        cursor = match.end()
    output.append(
        _convert_inline_plain(
            text[cursor:],
            context=context,
            allow_footnotes=allow_footnotes,
        )
    )
    return "".join(output)


def _convert_inline_plain(
    text: str,
    *,
    context: RenderContext,
    allow_footnotes: bool,
) -> str:
    output: list[str] = []
    cursor = 0
    for match in re.finditer(r"`(.+?)`", text):
        output.append(
            _convert_text_segment(
                text[cursor:match.start()],
                context=context,
                allow_footnotes=allow_footnotes,
            )
        )
        output.append(f"<code>{html.escape(match.group(1), quote=True)}</code>")
        cursor = match.end()
    output.append(
        _convert_text_segment(
            text[cursor:],
            context=context,
            allow_footnotes=allow_footnotes,
        )
    )
    return "".join(output)


def _convert_text_segment(
    text: str,
    *,
    context: RenderContext,
    allow_footnotes: bool,
) -> str:
    if not text:
        return ""

    spans = extract_furigana_spans(text)
    if not spans:
        return _replace_special_tokens(
            html.escape(text, quote=True),
            context=context,
            allow_footnotes=allow_footnotes,
        )

    output: list[str] = []
    cursor = 0
    for span in spans:
        output.append(
            _replace_special_tokens(
                html.escape(text[cursor:span.start], quote=True),
                context=context,
                allow_footnotes=allow_footnotes,
            )
        )
        output.append(
            f"<ruby>{html.escape(span.written, quote=True)}<rt>{html.escape(span.reading, quote=True)}</rt></ruby>"
        )
        cursor = span.end
    output.append(
        _replace_special_tokens(
            html.escape(text[cursor:], quote=True),
            context=context,
            allow_footnotes=allow_footnotes,
        )
    )
    return "".join(output)


def _replace_special_tokens(
    text: str,
    *,
    context: RenderContext,
    allow_footnotes: bool,
) -> str:
    rendered = INLINE_TIMESTAMP_PATTERN.sub(
        lambda match: _render_time(match.group(1)),
        text,
    )
    if allow_footnotes:
        rendered = re.sub(
            r"\*(\d+)",
            lambda match: _render_footnote(match.group(1), context=context),
            rendered,
        )
    return rendered


def _render_footnote(number: str, *, context: RenderContext) -> str:
    count = context.footnote_counts[number] + 1
    context.footnote_counts[number] = count
    ref_id = f"ref-{number}-{count}"
    context.first_footnote_ids.setdefault(number, ref_id)
    return f'<a href="#glossary-{number}" id="{ref_id}" class="footnote">*{number}</a>'


def _render_time(value: str) -> str:
    cleaned = value.strip("[]")
    parts = [int(part) for part in cleaned.split(":")]
    if len(parts) == 2:
        minutes, seconds = parts
        iso_value = f"PT{minutes}M{seconds}S"
    else:
        hours, minutes, seconds = parts
        iso_value = f"PT{hours}H{minutes}M{seconds}S"
    return f'<time datetime="{iso_value}">{html.escape(cleaned, quote=True)}</time>'


def _load_template_css() -> str:
    template_path = (
        pathlib.Path(__file__).resolve().parent.parent / "templates" / "default_style.css"
    )
    if template_path.exists():
        return template_path.read_text(encoding="utf-8").strip()

    return """
body { margin: 0; font-family: sans-serif; padding: 2rem; }
main { max-width: 960px; margin: 0 auto; }
""".strip()


def _wrap_in_html(title: str, page_html: str) -> str:
    escaped_title = html.escape(title, quote=True)
    css = _load_template_css()
    return f"""<!DOCTYPE html>
<html lang="ja">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escaped_title}</title>
  <style>
{css}
  </style>
</head>
<body>
{page_html}
</body>
</html>"""
