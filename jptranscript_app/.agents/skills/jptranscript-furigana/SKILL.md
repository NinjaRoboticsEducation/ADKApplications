---
name: jptranscript-furigana
description: Add hiragana furigana to every kanji-containing word in Japanese text by appending the correct contextual reading in full-width parentheses, while preserving 100% of the original wording, order, punctuation, and content. Use when Codex needs to make Japanese transcripts, study materials, notes, articles, dialogue, or learner-facing text more readable without rewriting, cleaning, summarizing, or restructuring the source.
---

# JP Transcript Furigana

## Overview

Add furigana in hiragana to kanji-containing words so the text becomes easier to read for learners. Keep the original text completely intact apart from the furigana additions.

## Core Task

For each word or compound that contains kanji, append its hiragana reading immediately after the original written form using full-width parentheses:

```text
漢字（かんじ）
```

Use the reading that matches the word's meaning in context.

## Workflow

1. Read the full passage to understand context and likely readings.
2. Identify every lexical unit that contains one or more kanji.
3. Append hiragana furigana in full-width parentheses after each kanji-containing unit.
4. Preserve all original spacing, punctuation, line breaks, labels, and wording.
5. Re-read the output and verify that nothing changed except the furigana additions.

## Furigana Rules

### Apply Furigana to All Kanji-Containing Words

- Add furigana to all words and compounds that contain kanji, whether common or advanced.
- This includes ordinary nouns, verbs, adjectives, adverbs, set phrases, names when readable from context, and compounds such as `日本語`, `図書館`, and `合格`.
- Apply furigana even to easy kanji such as `私`.

### Use Hiragana Only

- Write readings in hiragana, not katakana or romaji.
- Use full-width parentheses `（ ）` with no extra spaces.

### Do Not Add Furigana to Kana-Only or Non-Japanese Tokens

- Do not add furigana to words written entirely in hiragana.
- Do not add furigana to words written entirely in katakana.
- Do not add furigana to Latin letters, numbers, or symbols unless the token also contains kanji.
- Keep items such as `N1`, `AI`, and punctuation unchanged.

### Preserve Mixed Kanji-Kana Words as Written

- For words that mix kanji and kana, keep the original spelling and append the reading after the full written word.
- Examples:
  - `食べる（たべる）`
  - `取り組む（とりくむ）`
  - `見直し（みなおし）`

### Use Contextual Readings

- Choose the reading that matches the actual meaning in the sentence.
- Distinguish homographs by context rather than defaulting to the most common reading.
- Treat personal names, place names, and organization names carefully.
- If a reading is genuinely ambiguous and cannot be safely inferred from context, do not invent an obviously speculative reading.

### Avoid Double Annotation

- If a token already includes furigana immediately after it in the required format, do not add a second one.
- Preserve existing correct annotations as-is.

## Hard Guardrails

- Preserve 100% of the original content.
- Do not rewrite, clean up, summarize, restructure, or paraphrase the text.
- Do not alter punctuation, speaker labels, timestamps, Markdown, or line breaks except to insert furigana.
- Do not convert words into dictionary form or change inflection.
- Do not remove fillers, hesitations, or transcription artifacts; this skill only adds furigana.
- Do not split or reorder sentences.

## Output Rules

- Return only the fully annotated text unless the user explicitly asks for explanation.
- Keep the original formatting and layout intact.
- Insert each reading immediately after the corresponding kanji-containing word.
- Do not add headings, notes, or labels such as `変換後`.

## Quick Verification Checklist

Before finalizing, confirm:

- Every kanji-containing word now has a hiragana reading, unless the reading was genuinely not inferable.
- No kana-only word received furigana.
- No original wording changed.
- All parentheses are full-width.
- Every reading matches the context of the sentence.

## Example

Input:

```text
私の目標は日本語能力試験のN1に合格することです。図書館で毎日勉強しています。
```

Output:

```text
私（わたし）の目標（もくひょう）は日本語（にほんご）能力（のうりょく）試験（しけん）のN1に合格（ごうかく）することです。図書館（としょかん）で毎日（まいにち）勉強（べんきょう）しています。
```

Another mixed-script example:

```text
入力: 新しい計画を見直して取り組みます。
出力: 新しい（あたらしい）計画（けいかく）を見直して（みなおして）取り組みます（とりくみます）。
```
