---
name: yttranscript-generator
description: Generate complete, shadowing-ready YouTube transcripts from a provided YouTube URL. Use when Codex needs to extract or create a timestamped transcript for an entire video, preserve the original spoken language, detect missing subtitle coverage, and fall back to full-audio transcription when captions are absent or incomplete.
---

# yttranscript-generator

## Quick Start

Run the bundled script first:

```bash
python3 scripts/generate_transcript.py "<youtube-url>"
```

- Add `--lang ja` or another BCP-47 language code when the spoken language is known.
- Add `--force-asr --whisper-model large` when subtitle coverage looks suspicious or the user explicitly wants a full audio transcription pass.
- Add `--stdout` only when the transcript is short enough to paste safely; otherwise let the script write into `./transcripts/`.

## Workflow

1. Inspect the YouTube link with `yt-dlp`.
2. Prefer human subtitles in the spoken language.
3. Use automatic captions only when human subtitles are unavailable.
4. Reject caption output if it fails the completeness checks below.
5. Fall back to Whisper ASR for a full-audio transcription pass when subtitles are missing or incomplete.
6. Preserve the original spoken language unless the user explicitly asks for a separate translation.
7. Verify the beginning, ending, and any long silence gaps before presenting the transcript as complete.

## Completeness Rules

- Treat a transcript as complete only when the first cue begins within 3 seconds of the video start.
- Treat a transcript as complete only when the final cue ends within 3 seconds of the reported video duration.
- Treat a transcript as complete only when covered speech reaches at least 98% of the video runtime.
- Treat any unexplained silent gap longer than 12 seconds as a failure unless the video genuinely contains non-speech content there.
- Prefer a slower full-audio ASR run over handing back a shorter but partial subtitle file.
- Never summarize, paraphrase, or silently omit sponsor reads, intros, outros, or repeated phrases.
- Preserve fillers, false starts, corrections, and repetitions because shadowing depends on the original rhythm.

## Output Rules

- Format every line as `[HH:MM:SS.mmm --> HH:MM:SS.mmm] text`.
- Keep segments short enough for shadowing. Split long lines instead of dropping detail.
- Mark uncertain speech with `[unclear]` or `[inaudible Xs]` instead of guessing.
- Preserve non-speech markers only when they help the learner follow the audio, such as `[music]`, `[laughter]`, or `[applause]`.
- If the user also wants a translation, keep the source-language transcript intact and put the translation in a separate section or file.

## Tooling

- `scripts/generate_transcript.py` handles metadata inspection, caption download, caption completeness checks, optional Whisper fallback, and normalized output.
- Read `references/shadowing-output.md` when you need the exact acceptance criteria or formatting standards.
- Install missing dependencies locally rather than changing system tooling when possible.
  - Minimum dependency: `yt-dlp`
  - ASR fallback dependencies: `openai-whisper` or a compatible `whisper` CLI, plus `ffmpeg`

## Delivery

- Default output path: `./transcripts/<video-id>-<sanitized-title>.txt`
- Open the generated file and spot-check the first cues, last cues, and any flagged long gaps before sending the transcript to the user.
- If the fallback ASR tools are missing and captions fail completeness checks, stop and report that a complete transcript could not yet be produced.
