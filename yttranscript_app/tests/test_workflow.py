import asyncio
import json
import re

import yttranscript_app.agent as agent_module
from yttranscript_app.tools import job_state
from yttranscript_app.tools.youtube_transcript import TranscriptBuildResult
from yttranscript_app.tools.youtube_transcript import Segment
from yttranscript_app.workflow import PipelineResult
from yttranscript_app.workflow import ProgressUpdate
from yttranscript_app.workflow import run_transcript_pipeline
from google.genai import types


class FakeClient:
    model = "gemma4-agent"

    def __init__(self) -> None:
        self.calls = []

    def chat_json(self, system_prompt: str, user_prompt: str, *, schema):
        self.calls.append((system_prompt, user_prompt, schema))
        cue_count = len(re.findall(r"(?m)^\d+\.\s+\[", user_prompt))
        return {
            "sections": [
                {
                    "title": "Opening section",
                    "start_index": 1,
                    "end_index": cue_count,
                }
            ],
            "takeaways": ["Track recurring English phrasing while shadowing."],
        }


class NoTakeawayClient:
    model = "gemma4-agent"

    def __init__(self) -> None:
        self.calls = []

    def chat_json(self, system_prompt: str, user_prompt: str, *, schema):
        self.calls.append((system_prompt, user_prompt, schema))
        cue_count = len(re.findall(r"(?m)^\d+\.\s+\[", user_prompt))
        return {
            "sections": [
                {
                    "title": "Opening section",
                    "start_index": 1,
                    "end_index": cue_count,
                }
            ],
            "takeaways": [],
        }


def _fake_generate_transcript(url: str, *, output_path, lang=None, **kwargs):
    content = """# Title: Example video
# URL: https://www.youtube.com/watch?v=dQw4w9WgXcQ
# Source: manual subtitles (en, vtt)
# Language: en
# Duration: 00:00:08.000
# QA: coverage=100.0% first_gap=0.0s last_gap=0.0s max_internal_gap=0.0s

[00:00:00.000 --> 00:00:04.000] First cue from the video.
[00:00:04.000 --> 00:00:08.000] Second cue from the video.
"""
    output_path.write_text(content, encoding="utf-8")
    return TranscriptBuildResult(
        canonical_url=url,
        metadata={
            "id": "dQw4w9WgXcQ",
            "title": "Example video",
            "webpage_url": url,
            "duration": 8.0,
        },
        segments=(
            Segment(start=0.0, end=4.0, text="First cue from the video."),
            Segment(start=4.0, end=8.0, text="Second cue from the video."),
        ),
        report={
            "coverage": 1.0,
            "first_gap": 0.0,
            "last_gap": 0.0,
            "max_internal_gap": 0.0,
        },
        source_label="manual subtitles (en, vtt)",
        language=lang or "en",
        content=content,
        output_path=output_path,
    )


def test_run_transcript_pipeline_writes_html_manifest_and_qa(monkeypatch, tmp_path):
    monkeypatch.setattr(job_state, "WORK_DIR", tmp_path / "Work")
    monkeypatch.setattr(job_state, "OUTPUT_DIR", tmp_path / "Output")
    monkeypatch.setattr("yttranscript_app.workflow.generate_transcript", _fake_generate_transcript)
    client = FakeClient()

    result = run_transcript_pipeline(
        "Please build shadowing material for https://youtu.be/dQw4w9WgXcQ",
        client=client,
    )

    assert result.output_path.exists()
    assert result.manifest_path.exists()
    assert result.qa_summary_path.exists()
    assert result.output_path.parent == tmp_path / "Output"
    assert client.calls

    html = result.output_path.read_text(encoding="utf-8")
    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    qa_summary = json.loads(result.qa_summary_path.read_text(encoding="utf-8"))

    assert 'class="hero"' in html
    assert 'id="runtime-warning"' in html
    assert 'class="dict-word"' in html
    assert manifest["stages"]["transcript"]["status"] == "completed"
    assert manifest["stages"]["shadowing_html"]["status"] == "completed"
    assert qa_summary["transcript"]["cue_count"] == 2
    assert qa_summary["shadowing_html"]["cue_count"] == 2


def test_run_transcript_pipeline_emits_progress_updates(monkeypatch, tmp_path):
    monkeypatch.setattr(job_state, "WORK_DIR", tmp_path / "Work")
    monkeypatch.setattr(job_state, "OUTPUT_DIR", tmp_path / "Output")
    monkeypatch.setattr("yttranscript_app.workflow.generate_transcript", _fake_generate_transcript)
    client = FakeClient()
    updates: list[ProgressUpdate] = []

    run_transcript_pipeline(
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        client=client,
        progress_callback=updates.append,
    )

    assert updates[0].stage == "pipeline"
    assert updates[0].status == "started"
    assert any(update.stage == "transcript" and update.status == "started" for update in updates)
    assert any(update.stage == "structure" and update.status == "completed" for update in updates)
    assert updates[-1].stage == "shadowing_html"
    assert updates[-1].status == "completed"


def test_run_transcript_pipeline_succeeds_when_model_returns_no_takeaways(monkeypatch, tmp_path):
    monkeypatch.setattr(job_state, "WORK_DIR", tmp_path / "Work")
    monkeypatch.setattr(job_state, "OUTPUT_DIR", tmp_path / "Output")
    monkeypatch.setattr("yttranscript_app.workflow.generate_transcript", _fake_generate_transcript)
    client = NoTakeawayClient()

    result = run_transcript_pipeline(
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        client=client,
    )

    html = result.output_path.read_text(encoding="utf-8")
    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))

    assert 'class="takeaways"' in html
    assert "Key Takeaways" in html
    assert manifest["stages"]["shadowing_html"]["status"] == "completed"


def test_agent_streams_progress_events(monkeypatch, tmp_path):
    def fake_run_transcript_pipeline(user_input: str, *, client=None, progress_callback=None) -> PipelineResult:
        assert "dQw4w9WgXcQ" in user_input
        assert progress_callback is not None
        progress_callback(
            ProgressUpdate(
                stage="pipeline",
                status="started",
                message="Started YouTube transcript build.",
                job_id="job-123",
            )
        )
        progress_callback(
            ProgressUpdate(
                stage="transcript",
                status="completed",
                message="[1/4] Transcript acquisition completed.",
                stage_index=1,
                completed=2,
                total=2,
                job_id="job-123",
            )
        )
        return PipelineResult(
            job_id="job-123",
            output_path=tmp_path / "out.html",
            manifest_path=tmp_path / "manifest.json",
            qa_summary_path=tmp_path / "qa_summary.json",
            source_type="youtube",
            source_label="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        )

    monkeypatch.setattr(agent_module, "run_transcript_pipeline", fake_run_transcript_pipeline)

    class FakeSession:
        events = []

    class FakeContext:
        invocation_id = "inv-1"
        branch = "root"
        session = FakeSession()
        user_content = types.Content(
            role="user",
            parts=[types.Part.from_text(text="https://youtu.be/dQw4w9WgXcQ")],
        )

    async def collect_events():
        events = []
        async for event in agent_module.root_agent._run_async_impl(FakeContext()):
            events.append(event)
        return events

    events = asyncio.run(collect_events())

    progress_events = [event for event in events if event.partial]
    final_event = events[-1]

    assert len(progress_events) == 2
    assert "Started YouTube transcript build." in progress_events[0].content.parts[0].text
    assert "Transcript acquisition completed." in progress_events[1].content.parts[0].text
    assert final_event.partial is None
    assert "Shadowing materials build completed." in final_event.content.parts[0].text
