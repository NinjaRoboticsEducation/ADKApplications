"""
ADK entrypoint for jptranscript_app.

The root agent is intentionally lightweight. Large transcript artifacts are
processed and persisted by ``workflow.py`` instead of being kept in ADK session
state, which keeps local Gemma runs viable for long Japanese content.
"""

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


# =====================================================================
# 1. Root Agent
# =====================================================================
# This file follows the same "guided tour" spirit as the beginner-friendly
# hello_world example in the repository root.
#
# The important difference is architectural:
# - `hello_world/agent.py` lets the model think and talk directly.
# - `jptranscript_app/agent.py` acts more like a traffic controller.
#
# The heavy transcript work lives in `workflow.py`, where large artifacts are
# written to disk stage by stage. The ADK root agent stays small, streams
# progress updates back to the chat UI, and only returns a final summary when
# the file-backed workflow has finished.

class JPTranscriptPipelineAgent(BaseAgent):
    """Root ADK agent that delegates transcript work to the local pipeline."""

    async def _run_async_impl(
        self,
        ctx: InvocationContext,
    ) -> AsyncGenerator[Event, None]:
        # -------------------------------------------------------------
        # Section A: Read the user's transcript request
        # -------------------------------------------------------------
        # The ADK web app may provide the latest user message directly in
        # `ctx.user_content`. If not, we fall back to the last user event in the
        # session history so the workflow can still run.
        user_input = _extract_user_text(ctx)
        loop = asyncio.get_running_loop()
        progress_queue: asyncio.Queue[ProgressUpdate] = asyncio.Queue()

        def progress_callback(update: ProgressUpdate) -> None:
            # The pipeline runs in a worker thread. This callback safely hands
            # each progress update back to the main asyncio loop.
            loop.call_soon_threadsafe(progress_queue.put_nowait, update)

        # -------------------------------------------------------------
        # Section B: Start the file-backed workflow in the background
        # -------------------------------------------------------------
        # `run_transcript_pipeline` is synchronous on purpose because it writes
        # stage artifacts to disk and can call blocking local services such as
        # Ollama. We move it to a background thread so the ADK chat remains
        # responsive while work is happening.
        run_task = asyncio.create_task(
            asyncio.to_thread(
                run_transcript_pipeline,
                user_input,
                progress_callback=progress_callback,
            )
        )
        progress_task: asyncio.Task[ProgressUpdate] = asyncio.create_task(
            progress_queue.get()
        )

        try:
            # ---------------------------------------------------------
            # Section C: Stream progress into the ADK chat interface
            # ---------------------------------------------------------
            # The web UI looks "stuck" if nothing is emitted during long local
            # runs. We therefore wait on both:
            # 1. the pipeline task itself, and
            # 2. the queue of progress updates coming from that task.
            #
            # Every progress update becomes a partial ADK event, which the chat
            # interface can render live while the final HTML is still building.
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

            # Drain any last progress messages that may have arrived just before
            # the workflow completed so the user sees the full execution trail.
            with suppress(asyncio.QueueEmpty):
                while True:
                    yield _build_progress_event(ctx, progress_queue.get_nowait())

            result = run_task.result()
        except Exception as exc:  # pragma: no cover - exercised via behavior
            # ---------------------------------------------------------
            # Section D: Convert workflow failures into one safe reply
            # ---------------------------------------------------------
            # The underlying exception is still stored in state for debugging,
            # but the user gets a clear, retry-friendly message instead of a
            # raw stack trace.
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
            # Clean up the outstanding queue wait task so repeated runs in the
            # same session do not leave cancelled tasks behind.
            if not progress_task.done():
                progress_task.cancel()
                with suppress(asyncio.CancelledError):
                    await progress_task

        # -------------------------------------------------------------
        # Section E: Return the final completion event
        # -------------------------------------------------------------
        # Only small metadata goes back into ADK state. The large transcript,
        # intermediate markdown, and final HTML all stay on disk.
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
    """Pull transcript text from the current request or prior user events."""
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
        "No transcript input was provided. Paste Japanese text or provide a .txt file path."
    )


def _content_text_parts(content: types.Content | None) -> list[str]:
    """Collect plain text parts from an ADK content payload."""
    if not content or not content.parts:
        return []
    texts = []
    for part in content.parts:
        if part.text:
            texts.append(part.text)
    return texts


def _build_state_delta(result: PipelineResult) -> dict[str, object]:
    """Store a compact success summary in ADK session state."""
    return {
        "last_run_status": "completed",
        "last_job_id": result.job_id,
        "last_output_path": str(result.output_path),
        "last_manifest_path": str(result.manifest_path),
        "last_source_type": result.source_type,
        "last_source_label": result.source_label,
        "last_progress_stage": "completed",
        "last_progress_message": f"Build completed: {result.output_path.name}",
    }


def _build_progress_event(ctx: InvocationContext, update: ProgressUpdate) -> Event:
    """Convert one pipeline progress update into a partial ADK chat event."""
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
    """Build the final user-facing success message."""
    lines = [
        "HTML transcript build completed.",
        f"Output: {result.output_path}",
        f"Manifest: {result.manifest_path}",
    ]
    if result.warnings:
        lines.append("")
        lines.append("Warnings:")
        lines.extend(f"- {warning}" for warning in result.warnings)
    return "\n".join(lines)


def _format_failure_message(exc: Exception) -> str:
    """Translate internal exceptions into a calm retry-oriented explanation."""
    if isinstance(exc, PipelineError):
        reason = str(exc)
    else:
        reason = f"Unexpected pipeline error: {exc}"
    return (
        "The transcript build could not complete.\n"
        f"Reason: {reason}\n"
        "No destructive changes were made; you can retry after fixing the input or local model setup."
    )


# =====================================================================
# 2. ADK Application Wiring
# =====================================================================
# The ADK `App` wraps the root agent so `adk web` can discover and run it.
# Resumability is enabled so the session can keep lightweight progress metadata
# even though the large transcript artifacts live on disk.
root_agent = JPTranscriptPipelineAgent(
    name="jptranscript_pipeline",
    description=(
        "Processes Japanese transcript text with a file-backed local workflow "
        "and produces a learner-friendly HTML document."
    ),
)

app = App(
    name="jptranscript_app",
    root_agent=root_agent,
    resumability_config=ResumabilityConfig(is_resumable=True),
)
