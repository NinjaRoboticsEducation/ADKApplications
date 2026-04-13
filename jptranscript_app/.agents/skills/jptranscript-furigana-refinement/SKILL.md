---
name: jptranscript-furigana-refinement
description: Refine already-annotated Japanese furigana text for intermediate readers by removing furigana from a predefined common-word list on every occurrence and keeping furigana only on the first appearance of other annotated words, while preserving 100% of the original base text, wording, punctuation, and structure. Use when Codex needs to reduce furigana clutter in learner-facing Japanese transcripts, study notes, articles, or dialogue after a full-furigana pass.
---

# JP Transcript Furigana Refinement

## Overview

Reduce visual clutter in furigana-annotated Japanese text without changing the underlying content. Assume the input already contains furigana such as `漢字（かんじ）`, and refine those annotations for an intermediate learner level.

## Core Goal

Apply these rules in order:

1. Remove furigana from every occurrence of words in the common-word list.
2. For all other annotated words, keep furigana only on their first three appearance.
3. Leave the original wording and formatting unchanged apart from the furigana removals required by the rules above.

If an example conflicts with the explicit rules above, prioritize the explicit rules.

## Expected Input

This skill expects Japanese text that already contains furigana annotations in the form:

```text
漢字（かんじ）
```

Do not use this skill to generate missing furigana from scratch. Use it after a full-furigana workflow such as `$jptranscript-furigana`.

## Workflow

1. Read the text from top to bottom once.
2. Identify all existing furigana annotations.
3. Remove furigana from all common-list matches.
4. Track first appearance for all remaining annotated words.
5. Keep furigana on the first appearance of each remaining word and remove it from later repetitions.
6. Verify that nothing changed in the base text except furigana deletion.

## Common-Word Removal Rule

Remove furigana every time these items appear with the listed reading:

`日本（にほん）, 私（わたし）, 行（い）, 中（なか）, 方（かた / ほう）, 思（おも）, 感（かん）, 何（なに / なん）, 皆（みな）, 知（し）, 間（あいだ）, 国（くに）, 約（やく）, 多（おお）, 人（ひと / にん）, 本当（ほんとう）, 行（おこな）, 大（おお）, 近（ちか）, 見（み）, 今回（こんかい）, 金（かね）, 買（か）, 来（く / き）, 人気（にんき）, 食（た）, 良（よ）, 入（い）, 聞（き）, 道（みち）, 立（た）, 日本語（にほんご）, 毎週（まいしゅう）, 会（あ）, 前（まえ）, 結構（けっこう）, 一番（いちばん）, 旅行（りょこう）, 話（はなし）, 後（あと）, 作（つく）, 自分（じぶん）, 彼（かれ）, 例（れい / たと）, 興味（きょうみ）, 最（もっと）, 言（い）, 今（いま）, 問題（もんだい）, 実（じつ）, 時（とき）, 出（で）, 決（き）, 一（ひと）, 場所（ばしょ）, 今日（きょう）, 最近（さいきん）, 年（ねん）, 月（がつ）, 日（ひ）, 分（ふん）, 秒（びょう）, 元気（げんき）, 考（かんが）, 元（もも）, 手（て）, 世界（せかい）, 先（さき）, 活動（かつどう）, 対（たい）, 上（うえ / あ）, 生活（せいかつ）, 時代（じだい）, 東京（とうきょう）, 頃（ころ）, 子供（こども）, 学校（がっこう）, 使（つか）`

## Matching Rules

### Match by Written Form and Reading

- Remove furigana from a common-list item only when both the written form and the reading match the list entry.
- For entries with multiple readings such as `方（かた / ほう）` or `何（なに / なん）`, remove furigana only when the annotation matches one of the listed readings in context.
- If the same written form appears with a different reading that is not listed, do not treat it as a common-list match.

### Apply Stem-Like Entries Conservatively

- Some common-list entries are stems such as `行（い）`, `食（た）`, `思（おも）`, `聞（き）`, and `使（つか）`.
- Apply these to straightforward inflected or okurigana forms when the written form and reading clearly correspond.
- Examples:
  - `行く（いく）` -> `行く`
  - `思った（おもった）` -> `思った`
  - `食べる（たべる）` -> `食べる`
  - `使って（つかって）` -> `使って`
- If the match is uncertain, keep the furigana rather than over-remove it.

## First-Appearance Rule for Other Words

- After removing common-list furigana, track the remaining annotated words from top to bottom across the entire input.
- Keep furigana on the first appearance only.
- Remove furigana from later repetitions of the same word.
- Treat identity conservatively as the same written form plus the same reading. This avoids collapsing homographs with different readings.
- For mixed kanji-kana forms, track the full written form as it appears, such as `見直し` or `取り組む`.

Examples:

- `桜（さくら）...桜（さくら）` -> keep the first `桜（さくら）`, change the second to `桜`
- `人気（にんき）` -> remove furigana every time because it is in the common list
- `人気（ひとけ）` -> not a common-list match, so apply the first-appearance rule instead

## Hard Guardrails

- Preserve 100% of the original base text.
- Do not rewrite, simplify, summarize, or restructure the transcript.
- Do not add new furigana where none existed.
- Do not change punctuation, spacing, speaker labels, line breaks, Markdown, or timestamps.
- Do not change kanji, kana, inflection, or sentence order.
- Only remove furigana annotations according to the rules of this skill.
- If the common-list entry itself appears questionable or unusual, treat the list literally rather than silently rewriting it.

## Output Rules

- Return only the refined text unless the user explicitly asks for explanation.
- Keep all surviving furigana in the original full-width parenthesis format.
- Remove only the furigana, not the written word it belongs to.
- Do not add notes such as `修正版` or `中級向け`.

## Quick Verification Checklist

Before finalizing, confirm:

- Every common-list match lost its furigana.
- Every non-common annotated word kept furigana only on its first appearance.
- No base wording changed.
- No new furigana was introduced.
- Homographs with different readings were handled conservatively.

## Example

Input:

```text
私（わたし）は日本（にほん）で桜（さくら）を見ました。桜（さくら）は本当（ほんとう）に綺麗（きれい）でした。
```

Output:

```text
私は日本で桜（さくら）を見ました。桜は本当に綺麗（きれい）でした。
```

Another example:

```text
入力: 人気（にんき）の場所（ばしょ）で食べる（たべる）料理（りょうり）は料理（りょうり）人（にん）が作った（つくった）ものです。
出力: 人気の場所で食べる料理（りょうり）は料理人が作ったものです。
```
