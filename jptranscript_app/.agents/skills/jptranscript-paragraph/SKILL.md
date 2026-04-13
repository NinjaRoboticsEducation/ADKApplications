---
name: jptranscript-paragraph
description: Restructure raw Japanese transcript content into a logically segmented Markdown document by inserting paragraph breaks, generating concise Japanese H2 subtitles, formatting dialogue turns, and optionally highlighting explicit term definitions, while preserving 100% of the original wording and content. Use when Codex needs to improve the readability of interviews, meetings, lectures, transcripts, or long Japanese text blocks through structural editing only, without summarizing, rewriting, or deleting content.
---

# JP Transcript Paragraph

## Overview

Transform a raw Japanese transcript block into a clean Markdown document with clear sections and readable formatting. Preserve every original word and detail; only change structure and presentation.

## Structural Editing Goal

Perform structural editing only. Improve clarity by reorganizing the presentation of the existing text, not by rewriting it.

Allowed structural changes:

- Insert paragraph breaks at genuine topic or idea shifts.
- Add concise Japanese H2 subtitles for each resulting section.
- Format dialogue turns with bold speaker names and a full-width colon.
- Optionally highlight explicit term-definition patterns when that can be done without changing wording.
- Add a Markdown table of contents based on the generated subtitles.

Disallowed changes:

- Rewriting or paraphrasing sentences.
- Deleting repetitions, hedges, or nuance-bearing phrases.
- Reordering information.
- Shortening, summarizing, or explaining the content.
- Inserting commentary beyond structural headings and table-of-contents items.

## Workflow

1. Read the entire text first to understand the logical flow.
2. Identify natural topic shifts or speaker-block transitions.
3. Divide the content into sections only where the topic or core idea genuinely changes.
4. Write one concise Japanese H2 subtitle for each section.
5. Add a short table of contents at the top using those subtitles.
6. Format dialogue and term-definition patterns without changing the underlying words.
7. Verify that every original word and idea still appears in the final output.

## Segmentation Rules

- Create a new paragraph only when the topic, subtopic, argument, example, or speaker block clearly shifts.
- Do not split by visual length alone.
- Keep closely related sentences together even if the block becomes long.
- Avoid creating overly fine-grained sections from minor transitions.
- If the transcript is one continuous idea, use one section only.

## Subtitle Rules

- Use `## ` Markdown headings for each section subtitle.
- Write subtitles in concise Japanese.
- Make each subtitle descriptive enough to help scanning, but do not over-explain.
- Base each subtitle on the section's content without adding new claims.
- Do not add extra prose around the subtitle.

## Table of Contents Rules

- Place the table of contents before the formatted body.
- Keep it minimal: use a flat Markdown bullet list with the generated subtitles in order.
- Do not add explanatory text other than an optional `**目次**` label.
- Do not include items that are not actual section subtitles.

## Dialogue Formatting

- If the text contains dialogue or interview turns, format the speaker label as `**名前**：`.
- Preserve the original speaker name exactly.
- Preserve the original utterance wording exactly.
- Apply this formatting turn by turn when speaker boundaries are clear.
- If the source already uses a colon, normalize only the presentation to bold name plus full-width colon.

## Term Definition Formatting

- If the text explicitly defines a term, you may highlight the term structurally.
- Prefer wording-preserving formats such as `【用語】とは、...` when the original sentence contains `とは`.
- Use `【用語】：...` only when it does not drop or alter original wording.
- Do not convert ordinary explanatory sentences into faux definitions.

## Hard Guardrails

- Preserve 100% completeness of the original content.
- Keep the original wording intact except for Markdown markup and clearly structural punctuation normalization.
- Do not add, remove, or replace factual information.
- Do not soften, strengthen, or reinterpret the author's claims.
- Do not omit filler, hesitation, or repetition, because this skill is not for transcript cleanup.
- Do not merge distant parts of the text if that would blur the original flow.
- If a structural transformation would require wording changes, do not perform it.

## Output Format

Return one Markdown document in this order:

1. Optional `**目次**`
2. Flat bullet list table of contents using the generated subtitles
3. The full formatted body

Within the body:

- Start each section with an H2 subtitle.
- Place the original text for that section directly under the subtitle.
- Keep all original content present across the full output.

## Quick Verification Checklist

Before finalizing, confirm:

- Every original sentence still appears.
- Paragraph boundaries follow topic shifts rather than arbitrary length.
- Every section has an H2 subtitle.
- Dialogue labels use bold speaker names with `：`.
- No subtitle or formatting choice implies a meaning not supported by the text.

## Example

Input:

```text
近年、サステナビリティへの関心が高まっています。これは単なる環境保護だけでなく、経済や社会の持続可能性も含む広い概念です。サステナビリティとは、環境、社会、経済の三つの観点から世の中を持続可能にしていくという考え方です。山田さん：この考え方をビジネスにどう活かすかが今後の課題ですね。田中さん：はい、全ての企業が無視できないテーマだと思います。特に若い世代の消費者は、企業の姿勢を厳しく見ています。
```

Output:

```markdown
**目次**
- サステナビリティの概要
- ビジネスにおける重要性

## サステナビリティの概要
近年、サステナビリティへの関心が高まっています。これは単なる環境保護だけでなく、経済や社会の持続可能性も含む広い概念です。【サステナビリティ】とは、環境、社会、経済の三つの観点から世の中を持続可能にしていくという考え方です。

## ビジネスにおける重要性
**山田さん**：この考え方をビジネスにどう活かすかが今後の課題ですね。
**田中さん**：はい、全ての企業が無視できないテーマだと思います。特に若い世代の消費者は、企業の姿勢を厳しく見ています。
```

Use this skill for structural readability improvements only. If the task also requires filler removal or transcript cleanup, combine it with a separate cleanup workflow rather than doing both implicitly.
