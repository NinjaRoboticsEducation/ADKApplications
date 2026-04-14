# Shadowing Output Standard

Use this reference when generating or reviewing the final transcript.

## Required transcript line format

Write each cue as:

```text
[HH:MM:SS.mmm --> HH:MM:SS.mmm] transcript text
```

Example:

```text
[00:00:03.120 --> 00:00:05.480] Welcome back to the channel.
[00:00:05.480 --> 00:00:08.020] Today we're going to practice connected speech.
```

## What "complete" means

- The first cue starts within 3 seconds of the video start.
- The final cue ends within 3 seconds of the reported video duration.
- Covered speech reaches at least 98% of the full runtime.
- No unexplained gap longer than 12 seconds remains in the delivered transcript.
- Missing or doubtful sections are marked explicitly instead of being skipped.

## What to preserve

- Keep the original spoken language.
- Keep fillers, repetitions, repairs, false starts, and discourse markers.
- Keep audible non-speech markers only when they help the learner follow timing.
- Keep short hesitations when they materially affect rhythm.

## What to avoid

- Do not summarize.
- Do not silently compress repeated lines.
- Do not rewrite spoken grammar into polished written grammar.
- Do not replace the source transcript with a translation.

## Handling uncertainty

- Use `[unclear]` for short uncertain words.
- Use `[inaudible 2.4s]` when a longer span cannot be recovered reliably.
- If a gap is too large to trust, rerun with full-audio ASR instead of guessing.

## Final QA checklist

1. Compare the first timestamp against the actual start of speech.
2. Compare the last timestamp against the video duration.
3. Scan for long gaps and confirm they are real silence or music-only sections.
4. Confirm the transcript remains in the source language.
5. Confirm the output can be shadowed line by line without missing chunks.
