"""ADK entrypoint for yttranscript_app."""

from __future__ import annotations

import asyncio
from contextlib import suppress
from typing import AsyncGenerator

from google.adk.agents import BaseAgent, InvocationContext
from google.adk.apps.app import App, ResumabilityConfig
from google.adk.events import Event
from google.adk.events.event_actions import EventActions
from google.genai import types

from .workflow import PipelineError, PipelineResult, ProgressUpdate, run_transcript_pipeline


class YTTranscriptPipelineAgent(BaseAgent):
    """Root ADK agent that delegates YouTube transcript work to the local pipeline."""

    async def _run_async_impl(
        self,
        ctx: InvocationContext,
    ) -> AsyncGenerator[Event, None]:
        user_input = _extract_user_text(ctx)
        loop = asyncio.get_running_loop()
        progress_queue: asyncio.Queue[ProgressUpdate] = asyncio.Queue()

        def progress_callback(update: ProgressUpdate) -> None:
            loop.call_soon_threadsafe(progress_queue.put_nowait, update)

        run_task = asyncio.create_task(
            asyncio.to_thread(
                run_transcript_pipeline,
                user_input,
                progress_callback=progress_callback,
            )
        )
        progress_task: asyncio.Task[ProgressUpdate] = asyncio.create_task(progress_queue.get())

        try:
            while True:
                done, _ = await asyncio.wait(
                    {run_task, progress_task},
                    return_when=asyncio.FIRST_COMPLETED,
                )
                if progress_task in done:
                    update = progress_task.result()
                    yield _build_progress_event(ctx, update)
                    progress_task = asyncio.create_task(progress_queue.get())

                if run_task in done:
                    break

            with suppress(asyncio.QueueEmpty):
                while True:
                    yield _build_progress_event(ctx, progress_queue.get_nowait())

            result = run_task.result()
        except Exception as exc:  # pragma: no cover - exercised via behavior
            failure_message = _format_failure_message(exc)
            yield Event(
                invocation_id=ctx.invocation_id,
                author=self.name,
                branch=ctx.branch,
                actions=EventActions(
                    state_delta={
                        "last_run_status": "failed",
                        "last_error": str(exc),
                    }
                ),
                content=types.Content(
                    role="model",
                    parts=[types.Part.from_text(text=failure_message)],
                ),
            )
            return
        finally:
            if not progress_task.done():
                progress_task.cancel()
                with suppress(asyncio.CancelledError):
                    await progress_task

        yield Event(
            invocation_id=ctx.invocation_id,
            author=self.name,
            branch=ctx.branch,
            actions=EventActions(state_delta=_build_state_delta(result)),
            content=types.Content(
                role="model",
                parts=[types.Part.from_text(text=_format_success_message(result))],
            ),
        )


def _extract_user_text(ctx: InvocationContext) -> str:
    texts = _content_text_parts(ctx.user_content)
    if texts:
        return "\n".join(texts).strip()

    for event in reversed(ctx.session.events):
        if event.author != "user":
            continue
        texts = _content_text_parts(event.content)
        if texts:
            return "\n".join(texts).strip()

    raise PipelineError(
        "No YouTube URL was provided. Paste a supported YouTube link to build the shadowing page."
    )


def _content_text_parts(content: types.Content | None) -> list[str]:
    if not content or not content.parts:
        return []
    return [part.text for part in content.parts if part.text]


def _build_state_delta(result: PipelineResult) -> dict[str, object]:
    return {
        "last_run_status": "completed",
        "last_job_id": result.job_id,
        "last_output_path": str(result.output_path),
        "last_manifest_path": str(result.manifest_path),
        "last_qa_summary_path": str(result.qa_summary_path),
        "last_source_type": result.source_type,
        "last_source_label": result.source_label,
        "last_progress_stage": "completed",
        "last_progress_message": f"Build completed: {result.output_path.name}",
    }


def _build_progress_event(ctx: InvocationContext, update: ProgressUpdate) -> Event:
    return Event(
        invocation_id=ctx.invocation_id,
        author=root_agent.name,
        branch=ctx.branch,
        partial=True,
        content=types.Content(
            role="model",
            parts=[types.Part.from_text(text=f"{update.message}\n")],
        ),
    )


def _format_success_message(result: PipelineResult) -> str:
    lines = [
        "Shadowing materials build completed.",
        f"Output: {result.output_path}",
        f"Manifest: {result.manifest_path}",
        f"QA summary: {result.qa_summary_path}",
    ]
    if result.warnings:
        lines.append("")
        lines.append("Warnings:")
        lines.extend(f"- {warning}" for warning in result.warnings)
    return "\n".join(lines)


def _format_failure_message(exc: Exception) -> str:
    if isinstance(exc, PipelineError):
        reason = str(exc)
    else:
        reason = f"Unexpected pipeline error: {exc}"
    return (
        "The shadowing build could not complete.\n"
        f"Reason: {reason}\n"
        "No destructive changes were made; you can retry after fixing the input or local model setup."
    )


root_agent = YTTranscriptPipelineAgent(
    name="yttranscript_pipeline",
    description=(
        "Builds synchronized shadowing materials from a YouTube URL using a "
        "file-backed local workflow and an Ollama-hosted Gemma model."
    ),
)

app = App(
    name="yttranscript_app",
    root_agent=root_agent,
    resumability_config=ResumabilityConfig(is_resumable=True),
)
