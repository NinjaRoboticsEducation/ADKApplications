---
name: jptranscript-phase-glossary
description: Annotate difficult Japanese words, phrases, and grammar patterns in-place with sequential `*1`, `*2` style markers and add a learner-friendly glossary appendix explaining them in Japanese at the end of the document. Use when Codex needs to help intermediate learners understand challenging Japanese transcript content, articles, notes, or dialogue without changing the original wording, formatting, furigana, or structure except for inserting annotation markers.
---

# JP Transcript Phrase Glossary

## Overview

Help learners understand difficult Japanese by marking challenging expressions directly in the text and explaining them afterward in a glossary. Preserve the original document exactly, except for inserting numbered annotation markers such as `*1`.

## Core Goal

Perform two actions only:

1. Insert sequential `*1`, `*2`, `*3` style markers after difficult words, phrases, or sentence patterns in the original text.
2. Add a glossary appendix at the end explaining each marked item.

Do not rewrite, summarize, or comment on the passage itself.

## What to Annotate

Mark items that would genuinely help an intermediate learner, such as:

- Advanced grammar patterns such as `〜はおろか`, `〜に相違ない`, `〜ざるを得ない`, `〜にほかならない`
- Idiomatic phrases and set expressions
- Formal or abstract vocabulary that is hard to infer from context
- Sentence patterns whose nuance differs from a simpler synonym
- Words or phrases whose usage, register, or comparison would help comprehension

Do not over-annotate every unfamiliar noun. Prioritize phrases and patterns where explanation adds real learning value.

## Workflow

1. Read the full text first to understand context and difficulty level.
2. Select the words, phrases, or 文型 that are worth explaining.
3. Insert annotation markers in order of first appearance: `*1`, `*2`, `*3`, and so on.
4. Keep the entire original body intact apart from those markers.
5. After the original content, add a Markdown horizontal rule `---`.
6. Add the heading `### 言葉の解説 (Glossary)`.
7. Write one glossary entry for each marker, matching the numbering exactly.

## Marker Rules

- Insert the marker immediately after the full target phrase or pattern.
- For multi-word expressions, place the marker after the entire expression, not after each component.
- If the annotated phrase already has furigana, place the marker after the furigana block, for example:
  - `表現（ひょうげん）*1`
- Keep numbering sequential in order of first annotation.
- Reuse the same number only when you intentionally want the exact same glossary entry to apply again; otherwise annotate only the first meaningful occurrence to avoid clutter.

## Glossary Format

For each annotation, create a matching entry using this structure:

```markdown
1. 〜おかげで
* **意味 (Meaning):** ...
* **例文 (Examples):**
  * ...
  * ...
* **比較 (Comparison):**
  * ...
```

Guidelines:

- Use the same number as the in-text marker, but render the glossary list item as `1.` or `2.` etc.
- Quote or label the exact phrase being explained.
- `意味` should explain the nuance clearly in Japanese.
- `例文` should include at least one natural example sentence, preferably two when helpful.
- `比較` should compare the item with a similar expression, simpler alternative, synonym, antonym, or commonly confused form.
- If an antonym is unnatural, prefer a comparison with a near-synonym or contrasting pattern instead of forcing one.

## Hard Guardrails

- Preserve 100% of the original content and formatting, including furigana, punctuation, spacing, speaker labels, line breaks, and Markdown.
- Do not alter, remove, or paraphrase the original text.
- The only allowed change inside the original body is insertion of the annotation markers like `*1`.
- Put all teaching content in the appendix after `---`.
- Do not summarize the document or comment on its topic.
- Do not silently "fix" grammar, wording, or furigana while annotating.

## Selection Discipline

- Choose items that are meaningfully difficult for an intermediate learner.
- Avoid annotating very basic words unless they are confusing in context.
- Prefer one marker for a whole difficult phrase rather than multiple markers on its internal pieces.
- If a sentence contains several overlapping difficult patterns, annotate the most instructionally useful unit.

## Output Order

Return the final result in this order:

1. The full original content with inserted markers
2. A line containing only `---`
3. The heading `### 言葉の解説 (Glossary)`
4. The numbered glossary entries

## Quick Verification Checklist

Before finalizing, confirm:

- The original body is unchanged except for `*n` markers.
- Each in-text marker has exactly one matching glossary entry.
- The numbering is sequential.
- Each glossary entry includes `意味`, `例文`, and `比較`.
- Any existing furigana remained untouched.

## Example

Input:

```text
彼の成功は努力のおかげであり、その結果に相違ない。
```

Output:

```markdown
彼の成功は努力のおかげで*1あり、その結果に相違ない*2。

---

### 言葉の解説 (Glossary)

1. 〜おかげで
* **意味 (Meaning):** ある良い結果が、特定の原因や行動によってもたらされたことを示す表現です。感謝や肯定的な気持ちを含むことが多いです。
* **例文 (Examples):**
  * 友達が助けてくれたおかげで、宿題が終わりました。
  * 毎日練習したおかげで、上手に話せるようになりました。
* **比較 (Comparison):**
  * **「〜せいで」との違い:** 「〜おかげで」は良い結果に使いやすいですが、「〜せいで」は悪い結果や不満を表す時に使います。

2. 〜に相違ない
* **意味 (Meaning):** 強い確信をもって「きっとそうだ」と判断する時に使う硬めの表現です。
* **例文 (Examples):**
  * あの様子なら、彼は事情を知っているに相違ない。
  * 長年の経験があるので、彼女なら成功するに相違ない。
* **比較 (Comparison):**
  * **「〜に違いない」との違い:** どちらも強い確信を表しますが、「〜に相違ない」の方がやや硬く、書き言葉的です。
```

Use this skill for explanation and annotation only. If the text first needs cleanup, paragraphing, or furigana work, do those in separate steps.
