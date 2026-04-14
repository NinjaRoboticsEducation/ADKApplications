---
name: yttranscript-optimizer
description: Reformat raw transcripts into shadowing-friendly study notes without changing the original transcript content. Use when Codex needs to group a verbatim transcript into topic-based paragraphs, add a short subtitle before each paragraph block, and append a concise takeaway summary after the transcript while preserving 100% of the source transcript in its original order.
---

# yttranscript-optimizer

## Quick Start

Create a structured version of the raw transcript with this layout:

```markdown
## Structured Transcript

### Section 1: <subtitle>
<verbatim transcript content from the first topic block>

### Section 2: <subtitle>
<next verbatim transcript block>

## Key Takeaways
- <summary bullet 1>
- <summary bullet 2>
```

After restructuring, validate the result:

```bash
python3 scripts/validate_transcript_integrity.py raw.txt optimized.md --require-summary
```

## Workflow

1. Read the full raw transcript before changing its structure.
2. Detect topic shifts and group contiguous lines into paragraph blocks.
3. Add one subtitle line before each block using `### Section N: <subtitle>`.
4. Keep the transcript text itself verbatim and in the same order.
5. Add `## Key Takeaways` after the transcript and summarize the ideas there.
6. Run the integrity validator before delivering the optimized transcript.

## Non-Negotiable Rules

- Do not delete, rewrite, translate, or paraphrase transcript content.
- Do not reorder any source line or sentence.
- Do not correct grammar, punctuation, or filler words inside the transcript body.
- Do not compress repeated phrases.
- Do not merge the summary into the transcript body.
- Only add structure around the transcript:
  - `## Structured Transcript`
  - `### Section N: <subtitle>`
  - blank lines between blocks
  - `## Key Takeaways` after the transcript

## Paragraphing Rules

- Base paragraph breaks on topic changes, not on arbitrary fixed length.
- Keep each block large enough to hold a coherent subtopic.
- If the transcript already contains timestamps or speaker labels, preserve them exactly where they appear.
- If the raw transcript is one uninterrupted block, split it only at clear conceptual shifts.
- If a topic shift is ambiguous, prefer fewer blocks over risky over-segmentation.

## Subtitle Rules

- Write a short subtitle that helps the learner anticipate the section.
- Keep subtitles descriptive, not clever.
- Avoid adding facts that are not supported by the transcript.
- Keep the subtitle separate from the transcript text by placing it on its own `### Section N: ...` line.

## Summary Rules

- Place the summary only after the full transcript.
- Use short bullets under `## Key Takeaways`.
- Summaries may paraphrase ideas because they are supplemental notes, not transcript content.
- Do not let the summary replace any transcript block.

## Validation

- Run `scripts/validate_transcript_integrity.py` whenever the transcript came from a file.
- The validator removes only the structural markers defined by this skill and then compares the normalized transcript text against the original.
- If validation fails, fix the structure rather than editing the source transcript.
- Read `references/format-contract.md` when you need the exact structure, allowed additions, or validator assumptions.

## Delivery

- Default output should be a new file, not an in-place rewrite, unless the user explicitly asks otherwise.
- Keep the raw transcript available so the integrity check can be rerun.
- If the raw input is provided inline instead of as a file, still follow the same structure and manually confirm that all content remains present and in order.
