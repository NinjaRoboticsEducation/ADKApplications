---
name: jptranscript-optimization
description: Optimize raw Japanese transcript text by removing timestamps and non-content tags, fixing unnatural spacing, removing semantically empty filler words, and making minimal typo, grammar, and particle corrections while preserving 100% of the original meaning, nuance, and factual content. Use when Codex needs to clean ASR output, interviews, meetings, subtitles, or speaker-labeled Japanese transcripts without summarizing, rewriting, or inventing content.
---

# JP Transcript Optimization

## Overview

Refine raw Japanese transcript text into clean, natural Japanese while preserving the full content and intent of the source. Make the minimum necessary edits to improve readability and remove transcript noise.

## Editing Priority

Apply edits in this order:

1. Remove obvious technical artifacts.
2. Fix spacing and transcription formatting issues.
3. Remove semantically empty fillers.
4. Correct only clear, low-risk language mistakes.
5. Re-read the result and verify that no meaning, nuance, or factual detail was lost.

If an edit feels uncertain, keep the original wording.

## Allowed Edits

### 1. Cleanup

- Remove timestamps such as `[00:15:30]`, `(00:15)`, subtitle counters, and obvious non-content tags.
- Fix unnatural spacing between characters or words.
- Preserve meaningful speaker labels such as `鈴木さん:` or `司会:`.
- Preserve ordering, paragraph breaks, and turn structure when they help retain the transcript's meaning.

### 2. Filler Removal

- Remove fillers that add no semantic value, such as `あのー`, `えーっと`, `まあ`, `その`, and `ええ`, when they are clearly conversational padding.
- Remove sentence-ending fillers such as `ですね`, `ですよね`, and `よね` only when they function as padding rather than meaning.
- Keep words that may carry stance, hesitation, emphasis, or nuance if removing them would flatten the speaker's intent.
- Treat `なんか` conservatively. Keep it unless it is clearly empty, because it often carries tone or approximation.

### 3. Minimal Corrections

- Correct obvious typos, particle mistakes, repeated characters caused by transcription artifacts, and clearly broken grammar.
- Normalize lightly from spoken to readable written Japanese only when the meaning stays identical.
- Keep names, numbers, dates, uncertainty, hedging, and qualifiers exactly intact in substance.
- Prefer minimal punctuation cleanup over stylistic rewriting.

## Hard Guardrails

- Preserve 100% completeness of the content.
- Do not summarize, compress, or omit details.
- Do not invent missing words, explanations, or connective phrases.
- Do not rewrite for style beyond the minimum needed for clarity.
- Do not remove repetitions that carry emphasis, self-correction, or rhetorical effect.
- Do not convert the speaker's meaning into a stronger, weaker, more formal, or more certain claim.
- When uncertain whether something is filler or meaning-bearing, keep it.
- When uncertain how to correct a passage safely, leave it as-is.

## Output Rules

- Return only the cleaned transcript unless the user explicitly asks for commentary.
- Keep speaker labels that are part of the transcript.
- Keep segmentation that matters for readability or turn-taking.
- Do not add notes such as `修正後:` or `Cleaned version:` unless requested.

## Quick Decision Test

Before finalizing, check each edit with this test:

- Does this remove only noise, or does it remove meaning?
- Does this correction fix an obvious error, or am I guessing?
- Does this phrasing preserve the same nuance, confidence level, and factual claim?

If the answer is uncertain, revert that edit.

## Example

Input:

```text
[00:02:10] 鈴木さん: あのー、まあ、昨日の会議ですけどね、えーっと、配布したその資料が、なんか少し間違ってたんですよね。
```

Output:

```text
鈴木さん: 昨日の会議ですが、配布した資料がなんか少し間違っていました。
```

Another safe cleanup example:

```text
入力: 司会: こ　ん　に　ち　は。本日のテーマはですね、新しい料金改定についてです。
出力: 司会: こんにちは。本日のテーマは、新しい料金改定についてです。
```

Use restraint throughout. This is an editing task, not a rewriting task.
