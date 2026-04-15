"""Gemma-backed transcript structuring with deterministic validation and fallback."""

from __future__ import annotations

import json
import math
import pathlib
import re
from dataclasses import dataclass

from .ollama_client import OllamaChatClient, OllamaError

CUE_PATTERN = re.compile(
    r"^\[(?P<start>\d{2}:\d{2}:\d{2}\.\d{3}) --> (?P<end>\d{2}:\d{2}:\d{2}\.\d{3})\] (?P<text>.+)$"
)

DEFAULT_MAX_CUES_PER_CHUNK = 48
DEFAULT_MAX_CHARS_PER_CHUNK = 1800
STRUCTURE_SCHEMA = {
    "type": "object",
    "properties": {
        "sections": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "start_index": {"type": "integer"},
                    "end_index": {"type": "integer"},
                },
                "required": ["title", "start_index", "end_index"],
            },
        },
        "takeaways": {
            "type": "array",
            "items": {"type": "string"},
        },
    },
    "required": ["sections", "takeaways"],
}


class StructureError(RuntimeError):
    """Raised when transcript structuring cannot complete safely."""


@dataclass(frozen=True)
class TranscriptCue:
    """One normalized transcript cue."""

    index: int
    start_raw: str
    end_raw: str
    text: str

    @property
    def line(self) -> str:
        return f"[{self.start_raw} --> {self.end_raw}] {self.text}"


@dataclass(frozen=True)
class TranscriptMetadata:
    """Metadata parsed from the stage 1 transcript artifact."""

    title: str
    source_url: str
    source_label: str
    language: str
    duration: str


@dataclass(frozen=True)
class StructuredSection:
    """One structured transcript section with its original cues."""

    title: str
    cues: tuple[TranscriptCue, ...]


@dataclass(frozen=True)
class StructuredDocument:
    """A deterministic structured transcript representation."""

    metadata: TranscriptMetadata
    sections: tuple[StructuredSection, ...]
    takeaways: tuple[str, ...]


@dataclass(frozen=True)
class StructureChunk:
    """A local chunk of cues that can be sent to Gemma for grouping."""

    index: int
    cues: tuple[TranscriptCue, ...]


@dataclass(frozen=True)
class StructureChunkResult:
    """Validated structuring output for one cue chunk."""

    sections: tuple[StructuredSection, ...]
    takeaways: tuple[str, ...]
    used_fallback: bool = False


def _fallback_takeaways(sections: tuple[StructuredSection, ...]) -> tuple[str, ...]:
    """Synthesize stable takeaways when Gemma does not provide any."""
    if not sections:
        return (
            "Review the transcript in short passes and focus on matching the rhythm of each cue.",
        )

    first_title = sections[0].title.strip() or "the opening section"
    last_title = sections[-1].title.strip() or "the final section"
    cues_total = sum(len(section.cues) for section in sections)
    takeaways = [
        f"Start with {first_title} to get comfortable with the topic and speaking pace.",
        f"Use the section flow from {first_title} to {last_title} to organize repeated shadowing passes.",
        f"This transcript contains {cues_total} timed cues, so practice in short synchronized chunks instead of one full run.",
    ]
    return tuple(takeaways)


def parse_transcript_artifact(text: str) -> tuple[TranscriptMetadata, tuple[TranscriptCue, ...]]:
    """Parse the stage 1 transcript text into metadata plus timestamped cues."""
    lines = [line.rstrip() for line in text.splitlines()]
    header: dict[str, str] = {}
    cue_lines: list[str] = []
    for line in lines:
        if line.startswith("# "):
            raw = line[2:]
            if ":" in raw:
                key, value = raw.split(":", 1)
                header[key.strip().lower()] = value.strip()
            continue
        if line.strip():
            cue_lines.append(line)

    cues: list[TranscriptCue] = []
    for cue_index, line in enumerate(cue_lines, start=1):
        match = CUE_PATTERN.match(line)
        if not match:
            continue
        cues.append(
            TranscriptCue(
                index=cue_index,
                start_raw=match.group("start"),
                end_raw=match.group("end"),
                text=match.group("text").strip(),
            )
        )

    if not cues:
        raise StructureError("No parseable transcript cues were found in the transcript artifact.")

    metadata = TranscriptMetadata(
        title=header.get("title", "Untitled video"),
        source_url=header.get("url", ""),
        source_label=header.get("source", "unknown"),
        language=header.get("language", "unknown"),
        duration=header.get("duration", "00:00:00.000"),
    )
    return metadata, tuple(cues)


def chunk_cues(
    cues: tuple[TranscriptCue, ...],
    *,
    max_cues: int = DEFAULT_MAX_CUES_PER_CHUNK,
    max_chars: int = DEFAULT_MAX_CHARS_PER_CHUNK,
) -> tuple[StructureChunk, ...]:
    """Split cues into bounded chunks for the Gemma structuring stage."""
    chunks: list[StructureChunk] = []
    current: list[TranscriptCue] = []
    current_chars = 0
    chunk_index = 1

    for cue in cues:
        cue_chars = len(cue.line)
        would_exceed = bool(current) and (
            len(current) >= max_cues or current_chars + cue_chars > max_chars
        )
        if would_exceed:
            chunks.append(StructureChunk(index=chunk_index, cues=tuple(current)))
            chunk_index += 1
            current = []
            current_chars = 0
        current.append(cue)
        current_chars += cue_chars

    if current:
        chunks.append(StructureChunk(index=chunk_index, cues=tuple(current)))
    return tuple(chunks)


def _fallback_title(cues: tuple[TranscriptCue, ...], chunk_index: int) -> str:
    words = re.findall(r"[A-Za-z0-9][A-Za-z0-9'/-]*", cues[0].text)
    if words:
        phrase = " ".join(words[:6]).strip()
        return phrase[:60] or f"Section {chunk_index}"
    return f"Section {chunk_index}"


def _fallback_chunk(chunk: StructureChunk) -> StructureChunkResult:
    if not chunk.cues:
        return StructureChunkResult(sections=(), takeaways=(), used_fallback=True)
    midpoint = max(1, math.ceil(len(chunk.cues) / 2))
    ranges = (
        (chunk.cues[:midpoint], _fallback_title(chunk.cues[:midpoint], chunk.index)),
        (chunk.cues[midpoint:], _fallback_title(chunk.cues[midpoint:], chunk.index + 1)),
    )
    sections = tuple(
        StructuredSection(title=title, cues=tuple(cues))
        for cues, title in ranges
        if cues
    )
    return StructureChunkResult(sections=sections, takeaways=(), used_fallback=True)


def _load_structure_prompt() -> str:
    prompt_path = pathlib.Path(__file__).resolve().parent.parent / "prompts" / "structure_transcript.md"
    return prompt_path.read_text(encoding="utf-8").strip()


def _build_user_prompt(chunk: StructureChunk) -> str:
    cue_lines = "\n".join(
        f"{local_index}. {cue.line}"
        for local_index, cue in enumerate(chunk.cues, start=1)
    )
    return (
        "Group the following transcript cues into contiguous sections.\n\n"
        "Return JSON with local cue ranges only.\n"
        "Every cue must be covered exactly once.\n"
        "Do not output markdown.\n\n"
        "Transcript cues:\n"
        f"{cue_lines}\n"
    )


def _validate_chunk_response(
    chunk: StructureChunk,
    payload: dict[str, object],
) -> StructureChunkResult:
    raw_sections = payload.get("sections")
    raw_takeaways = payload.get("takeaways")
    if not isinstance(raw_sections, list) or not isinstance(raw_takeaways, list):
        raise StructureError("Structured response missing sections or takeaways array.")

    chunk_length = len(chunk.cues)
    cursor = 1
    sections: list[StructuredSection] = []
    for raw_section in raw_sections:
        if not isinstance(raw_section, dict):
            raise StructureError("Section payload must be an object.")
        title = str(raw_section.get("title", "")).strip() or _fallback_title(chunk.cues, chunk.index)
        try:
            start_index = int(raw_section.get("start_index"))
            end_index = int(raw_section.get("end_index"))
        except (TypeError, ValueError) as exc:
            raise StructureError("Section ranges must be integers.") from exc

        if start_index != cursor:
            raise StructureError("Section ranges must be contiguous and start at the expected cue.")
        if end_index < start_index or end_index > chunk_length:
            raise StructureError("Section range falls outside the chunk.")

        section_cues = chunk.cues[start_index - 1 : end_index]
        sections.append(StructuredSection(title=title, cues=tuple(section_cues)))
        cursor = end_index + 1

    if cursor != chunk_length + 1:
        raise StructureError("Section ranges did not cover the full chunk.")

    takeaways = tuple(
        item.strip()
        for item in raw_takeaways
        if isinstance(item, str) and item.strip()
    )
    return StructureChunkResult(sections=tuple(sections), takeaways=takeaways)


def structure_chunk(
    chunk: StructureChunk,
    *,
    client: OllamaChatClient,
) -> StructureChunkResult:
    """Structure one cue chunk with Gemma, then validate the response."""
    system_prompt = _load_structure_prompt()
    user_prompt = _build_user_prompt(chunk)

    for _attempt in range(2):
        try:
            payload = client.chat_json(system_prompt, user_prompt, schema=STRUCTURE_SCHEMA)
            return _validate_chunk_response(chunk, payload)
        except (OllamaError, StructureError, json.JSONDecodeError):
            continue
    return _fallback_chunk(chunk)


def dedupe_takeaways(items: list[str], *, limit: int = 8) -> tuple[str, ...]:
    """Keep the first distinct takeaways while preserving order."""
    seen: set[str] = set()
    results: list[str] = []
    for item in items:
        normalized = re.sub(r"\s+", " ", item).strip().lower()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        results.append(item.strip())
        if len(results) >= limit:
            break
    return tuple(results)


def structure_transcript(
    transcript_text: str,
    *,
    client: OllamaChatClient,
) -> StructuredDocument:
    """Convert a raw transcript artifact into deterministic structured sections."""
    metadata, cues = parse_transcript_artifact(transcript_text)
    chunks = chunk_cues(cues)
    all_sections: list[StructuredSection] = []
    all_takeaways: list[str] = []
    for chunk in chunks:
        result = structure_chunk(chunk, client=client)
        all_sections.extend(result.sections)
        all_takeaways.extend(result.takeaways)
    sections = tuple(all_sections)
    takeaways = dedupe_takeaways(all_takeaways)
    if not takeaways:
        takeaways = _fallback_takeaways(sections)
    return StructuredDocument(
        metadata=metadata,
        sections=sections,
        takeaways=takeaways,
    )


def render_structured_markdown(document: StructuredDocument) -> str:
    """Render the deterministic structured transcript markdown artifact."""
    lines = ["## Structured Transcript", ""]
    for index, section in enumerate(document.sections, start=1):
        lines.append(f"### Section {index}: {section.title}")
        lines.extend(cue.line for cue in section.cues)
        lines.append("")
    lines.append("## Key Takeaways")
    lines.extend(f"- {item}" for item in document.takeaways)
    return "\n".join(lines).strip() + "\n"
