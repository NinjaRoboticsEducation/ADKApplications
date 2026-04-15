from pathlib import Path

from yttranscript_app.tools.html_renderer import render_base_html
from yttranscript_app.tools.shadowing_html import optimize_shadowing_html
from yttranscript_app.tools.transcript_structure import StructuredDocument
from yttranscript_app.tools.transcript_structure import StructuredSection
from yttranscript_app.tools.transcript_structure import TranscriptCue
from yttranscript_app.tools.transcript_structure import TranscriptMetadata
from yttranscript_app.tools.transcript_structure import structure_transcript
from yttranscript_app.tools.validate_shadowing_html import validate_shadowing_html_content
from yttranscript_app.tools.validate_transcript_integrity import validate_transcript_integrity
from yttranscript_app.tools.youtube_transcript import canonicalize_youtube_url
from yttranscript_app.tools.youtube_transcript import detect_yt_dlp_runner


def test_canonicalize_youtube_url_normalizes_common_formats():
    assert canonicalize_youtube_url("https://youtu.be/dQw4w9WgXcQ") == (
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    )
    assert canonicalize_youtube_url(
        "https://www.youtube.com/shorts/dQw4w9WgXcQ?feature=share"
    ) == "https://www.youtube.com/watch?v=dQw4w9WgXcQ"


def test_detect_yt_dlp_runner_falls_back_to_python_module(monkeypatch):
    monkeypatch.delenv("YTTRANSCRIPT_YT_DLP_BIN", raising=False)
    monkeypatch.setattr("yttranscript_app.tools.youtube_transcript.shutil.which", lambda name: None)
    monkeypatch.setattr(
        "yttranscript_app.tools.youtube_transcript.importlib.util.find_spec",
        lambda name: object() if name == "yt_dlp" else None,
    )

    runner = detect_yt_dlp_runner()

    assert runner[1:] == ["-m", "yt_dlp"]


def test_validate_transcript_integrity_compares_only_transcript_cues():
    raw = """# Title: Example
# URL: https://www.youtube.com/watch?v=dQw4w9WgXcQ
# Source: manual subtitles (en, vtt)
# Language: en
# Duration: 00:00:08.000

[00:00:00.000 --> 00:00:04.000] First cue
[00:00:04.000 --> 00:00:08.000] Second cue
"""
    structured = """## Structured Transcript

### Section 1: Intro
[00:00:00.000 --> 00:00:04.000] First cue
[00:00:04.000 --> 00:00:08.000] Second cue

## Key Takeaways
- Keep the original cue text untouched.
"""

    report = validate_transcript_integrity(raw, structured)

    assert report.passed
    assert report.section_count == 1
    assert report.found_summary


def test_structure_transcript_synthesizes_takeaways_when_model_returns_none():
    transcript = """# Title: Example
# URL: https://www.youtube.com/watch?v=dQw4w9WgXcQ
# Source: manual subtitles (en, vtt)
# Language: en
# Duration: 00:00:08.000

[00:00:00.000 --> 00:00:04.000] First cue from the video.
[00:00:04.000 --> 00:00:08.000] Second cue from the video.
"""

    class NoTakeawayClient:
        def chat_json(self, system_prompt: str, user_prompt: str, *, schema):
            return {
                "sections": [
                    {"title": "Opening", "start_index": 1, "end_index": 2},
                ],
                "takeaways": [],
            }

    document = structure_transcript(transcript, client=NoTakeawayClient())

    assert document.takeaways
    assert "Opening" in document.takeaways[0]


def test_shadowing_html_builder_produces_valid_contract(tmp_path):
    document = StructuredDocument(
        metadata=TranscriptMetadata(
            title="Example video",
            source_url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            source_label="manual subtitles (en, vtt)",
            language="en",
            duration="00:00:08.000",
        ),
        sections=(
            StructuredSection(
                title="Opening",
                cues=(
                    TranscriptCue(
                        index=1,
                        start_raw="00:00:00.000",
                        end_raw="00:00:04.000",
                        text="The first sample cue.",
                    ),
                    TranscriptCue(
                        index=2,
                        start_raw="00:00:04.000",
                        end_raw="00:00:08.000",
                        text="The second sample cue.",
                    ),
                ),
            ),
        ),
        takeaways=("Focus on repeated phrasing.",),
    )
    base_html = render_base_html(
        title=document.metadata.title,
        source_url=document.metadata.source_url,
        document=document,
    )
    base_path = tmp_path / "base.html"
    base_path.write_text(base_html.html_content, encoding="utf-8")

    result = optimize_shadowing_html(
        base_path,
        document.metadata.source_url,
        output_path=tmp_path / "shadowing.html",
    )
    reference_html = (
        Path(__file__).resolve().parent.parent
        / "fixtures"
        / "html_reference"
        / "ai-agent-design-patterns.html"
    ).read_text(encoding="utf-8")
    report = validate_shadowing_html_content(
        result.html_content,
        youtube_url=document.metadata.source_url,
        reference_html=reference_html,
    )

    assert report.passed, report.errors
    assert "innerHTML" not in result.html_content
    assert result.cue_count == 2


def test_shadowing_html_validator_allows_pages_without_dictionary_spans_when_cues_have_no_english(tmp_path):
    document = StructuredDocument(
        metadata=TranscriptMetadata(
            title="Japanese sample",
            source_url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            source_label="manual subtitles (ja, vtt)",
            language="ja",
            duration="00:00:04.000",
        ),
        sections=(
            StructuredSection(
                title="Intro",
                cues=(
                    TranscriptCue(
                        index=1,
                        start_raw="00:00:00.000",
                        end_raw="00:00:04.000",
                        text="これは日本語だけの字幕です。",
                    ),
                ),
            ),
        ),
        takeaways=("一文ずつ区切って練習します。",),
    )
    base_html = render_base_html(
        title=document.metadata.title,
        source_url=document.metadata.source_url,
        document=document,
    )
    base_path = tmp_path / "base-ja.html"
    base_path.write_text(base_html.html_content, encoding="utf-8")

    result = optimize_shadowing_html(
        base_path,
        document.metadata.source_url,
        output_path=tmp_path / "shadowing-ja.html",
    )

    report = validate_shadowing_html_content(
        result.html_content,
        youtube_url=document.metadata.source_url,
    )

    assert report.passed, report.errors
