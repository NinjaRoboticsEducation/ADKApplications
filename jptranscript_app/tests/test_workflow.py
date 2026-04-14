import json
import re

import jptranscript_app.agent as agent_module
from jptranscript_app.tools import text_processing
from jptranscript_app.workflow import PipelineResult
from jptranscript_app.workflow import ProgressUpdate
from jptranscript_app.workflow import _repair_paragraph_document
from jptranscript_app.workflow import run_transcript_pipeline
from google.genai import types


class FakeClient:
    def __init__(self) -> None:
        self.calls = []

    def chat(self, system_prompt: str, user_prompt: str) -> str:
        self.calls.append(system_prompt)

        if system_prompt.startswith("Clean this Japanese transcript."):
            return user_prompt.replace("あのー、", "").replace("あのー", "")

        if system_prompt.startswith(
            "Restructure this Japanese transcript into a clear Markdown document."
        ):
            chunk = _extract_primary_chunk(user_prompt)
            speaker_match = re.search(r"([^：\n]+)：(.+)", chunk)
            if speaker_match:
                body = f"**{speaker_match.group(1)}**：{speaker_match.group(2).strip()}"
            else:
                body = chunk.strip()
            return f"## 天気の話\n{body}"

        if system_prompt.startswith(
            "Annotate difficult Japanese words, phrases, and grammar patterns in this text"
        ):
            chunk = _extract_primary_chunk(user_prompt)
            if "天気（てんき）" in chunk:
                annotated_body = chunk.replace("天気（てんき）", "天気（てんき）*1", 1)
                term = "天気（てんき）"
            else:
                annotated_body = chunk.replace("天気", "天気*1", 1)
                term = "天気"

            return (
                f"{annotated_body}\n\n"
                "---\n\n"
                "### 言葉の解説 (Glossary)\n\n"
                f"1. {term}\n"
                "* **意味:** 空模様のこと。\n"
                "* **例文:** 今日は天気がいいです。\n"
                "* **比較:** 「気候」は長期的な傾向です。\n"
            )

        raise AssertionError(f"Unexpected prompt received: {system_prompt[:80]}")


def _extract_primary_chunk(user_prompt: str) -> str:
    marker = "Primary chunk to process and return:\n\n"
    if marker in user_prompt:
        return user_prompt.split(marker, maxsplit=1)[1].strip()
    return user_prompt.strip()


def test_run_transcript_pipeline_writes_html_and_manifest(monkeypatch, tmp_path):
    monkeypatch.setattr(text_processing, "WORK_DIR", tmp_path / "Work")
    monkeypatch.setattr(text_processing, "OUTPUT_DIR", tmp_path / "Output")
    client = FakeClient()

    result = run_transcript_pipeline("山田：あのー、今日はいい天気です。", client=client)

    assert result.output_path.exists()
    assert result.output_path.parent == tmp_path / "Output"
    assert result.manifest_path.exists()
    assert any(prompt.startswith("Clean this Japanese transcript.") for prompt in client.calls)
    assert any(
        prompt.startswith("Restructure this Japanese transcript into a clear Markdown document.")
        for prompt in client.calls
    )
    assert any(
        prompt.startswith("Annotate difficult Japanese words, phrases, and grammar patterns in this text")
        for prompt in client.calls
    )

    html = result.output_path.read_text(encoding="utf-8")
    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))

    assert '<header class="hero">' in html
    assert "<nav aria-label=\"目次\">" in html
    assert 'class="layout"' in html
    assert "glossary-section" in html
    assert "<h1" in html and "天気の話" in html
    assert manifest["stages"]["optimization"]["status"] == "completed"
    assert manifest["stages"]["glossary"]["status"] == "completed"


def test_run_transcript_pipeline_emits_progress_updates(monkeypatch, tmp_path):
    monkeypatch.setattr(text_processing, "WORK_DIR", tmp_path / "Work")
    monkeypatch.setattr(text_processing, "OUTPUT_DIR", tmp_path / "Output")
    client = FakeClient()
    updates: list[ProgressUpdate] = []

    run_transcript_pipeline(
        "山田：あのー、今日はいい天気です。",
        client=client,
        progress_callback=updates.append,
    )

    assert updates[0].stage == "pipeline"
    assert updates[0].status == "started"
    assert any(
        update.stage == "optimization" and update.status == "started"
        for update in updates
    )
    assert any(
        update.stage == "paragraph" and update.status == "progress"
        for update in updates
    )
    assert updates[-1].stage == "beautify"
    assert updates[-1].status == "completed"


def test_agent_streams_progress_events(monkeypatch, tmp_path):
    def fake_run_transcript_pipeline(
        user_input: str,
        *,
        client=None,
        progress_callback=None,
    ) -> PipelineResult:
        assert user_input == "日本語の入力です。"
        assert progress_callback is not None
        progress_callback(
            ProgressUpdate(
                stage="pipeline",
                status="started",
                message="Started transcript build.",
                job_id="job-123",
            )
        )
        progress_callback(
            ProgressUpdate(
                stage="optimization",
                status="progress",
                message="[1/7] Optimization chunk 1/1 completed.",
                stage_index=1,
                completed=1,
                total=1,
                job_id="job-123",
            )
        )
        return PipelineResult(
            job_id="job-123",
            output_path=tmp_path / "out.html",
            manifest_path=tmp_path / "manifest.json",
            source_type="text",
            source_label="pasted transcript",
        )

    monkeypatch.setattr(
        agent_module,
        "run_transcript_pipeline",
        fake_run_transcript_pipeline,
    )

    class FakeSession:
        events = []

    class FakeContext:
        invocation_id = "inv-1"
        branch = "root"
        session = FakeSession()
        user_content = types.Content(
            role="user",
            parts=[types.Part.from_text(text="日本語の入力です。")],
        )

    async def collect_events():
        events = []
        async for event in agent_module.root_agent._run_async_impl(FakeContext()):
            events.append(event)
        return events

    import asyncio

    events = asyncio.run(collect_events())

    progress_events = [event for event in events if event.partial]
    final_event = events[-1]

    assert len(progress_events) == 2
    assert "Started transcript build." in progress_events[0].content.parts[0].text
    assert "Optimization chunk 1/1 completed." in progress_events[1].content.parts[0].text
    assert final_event.partial is None
    assert "HTML transcript build completed." in final_event.content.parts[0].text


def test_repair_paragraph_document_improves_title_and_broken_heading():
    markdown = """## 本文
今日はそんな作品を見るときに知っていると役立つ言葉をいくつかご紹介します。

## 実写と実．．．
実写とは、漫画やアニメの絵で作られた世界を本物の人間や景色で表現した作品のことです。
そして実写にすることを実写化と言います。
"""

    repaired = _repair_paragraph_document(markdown)

    assert repaired.startswith("# 作品を見るときに役立つ言葉")
    assert "## イントロダクション" in repaired
    assert "## 実写と実写化" in repaired


def test_repair_paragraph_document_uses_section_terms_for_headings():
    markdown = """## 皆 さ ん は 絵 を 描 く の
0:08
皆 さ ん は 絵 を 描 く の が 好 き で す か？
今 日 は 漢 字 の 絵 を 使 っ た 日 本 語 を い く つ か ご 紹 介 し ま す。

## そ こ か ら 素 晴 ら し い
そ こ か ら 素 晴 ら し い 計 画 や ア イ デ ア が あ っ て も、 実 際 に で き な け れ ば 意 味 が な い と い う 意 味 で す。
一つ目は 絵 本 です。
二つ目は 絵 日 記 です。
三つ目は 絵 画 です。
"""

    repaired = _repair_paragraph_document(markdown)

    assert repaired.startswith("# 漢字の絵を使った日本語")
    assert "## イントロダクション" in repaired
    assert "## 絵を使った言葉" in repaired
