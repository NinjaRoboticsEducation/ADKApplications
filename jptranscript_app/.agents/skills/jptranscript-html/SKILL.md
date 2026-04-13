---
name: jptranscript-html
description: Transform Japanese plain text or Markdown into a single polished, self-contained HTML file with semantic structure, embedded CSS, readable typography, ruby support, and linked glossary footnotes. Use when Codex needs to render transcripts, annotated learner materials, glossary-rich notes, or structured Japanese documents as downloadable HTML without changing the source content.
---

# JP Transcript HTML

## Overview

Convert input text or Markdown into a complete HTML5 document that is visually refined, easy to read, and semantically correct. Preserve 100% of the original content while expressing its structure with HTML and styling it with embedded CSS only.

## Core Goal

Create one complete HTML file that:

- Uses semantic HTML5 structure
- Preserves all original text content
- Embeds all CSS inside a `<style>` tag
- Converts furigana and glossary markers into useful HTML patterns
- Produces a professional, readable layout with no external dependencies

Return only a single block of complete HTML unless the user explicitly asks for something else.

## Workflow

1. Read the full input and identify its hierarchy before writing code.
2. Detect titles, section headings, subsections, paragraphs, lists, code-like material, keyboard shortcuts, glossary markers, and ruby-style furigana.
3. Build a semantic HTML structure that reflects the source faithfully.
4. Convert special inline patterns such as furigana and glossary markers into semantic HTML.
5. Add embedded CSS in the document `<head>` to produce a clean, elegant reading experience.
6. Re-check that all original content still appears in the final HTML.

## Document Structure

Always generate a complete HTML5 document:

```html
<!DOCTYPE html>
<html lang="ja">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>...</title>
  <style>
    /* embedded CSS only */
  </style>
</head>
<body>
  ...
</body>
</html>
```

Use semantic containers where appropriate, such as:

- `<main>` for the main content area
- `<article>` for the document body
- `<section>` for major content groups
- `<header>` for title and introductory metadata when present
- `<footer>` only if the source meaningfully contains footer-like material

## Hierarchy Mapping

### If the Input Is Markdown

- Convert Markdown headings to `<h1>`, `<h2>`, `<h3>`, and so on.
- Convert paragraphs to `<p>`.
- Convert bullet and numbered lists to `<ul>` and `<ol>`.
- Convert fenced code blocks or inline code to `<pre><code>` and `<code>`.
- Convert Markdown horizontal rules to `<hr>`.
- Preserve glossary sections and heading labels already present in the source.

### If the Input Is Plain Text

- Infer a title conservatively only when the structure clearly suggests one.
- Treat clear section labels or subtitle-like lines as headings.
- Convert ordinary text blocks to paragraphs.
- Keep line-group logic intact rather than flattening everything into one paragraph.
- If hierarchy is ambiguous, prefer simple paragraph structure over inventing headings.

## Inline Conversion Rules

### Furigana with `<ruby>`

- Convert patterns like `漢字（かんじ）` into semantic ruby markup:

```html
<ruby>漢字<rt>かんじ</rt></ruby>
```

- Preserve the original reading exactly.
- Apply ruby only when the parenthetical content is clearly furigana rather than ordinary prose.

### Emphasis, Code, and Shortcuts

- Use `<strong>` and `<em>` only when the source clearly indicates emphasis.
- Use `<code>` for inline technical notation or literal snippets.
- Use `<kbd>` for keyboard shortcuts such as `Ctrl + C`.

### Glossary Marker Links

- Detect footnote-style glossary markers such as `*1`, `*2`, and so on.
- Convert each marker in the body into a forward link to its glossary entry.
- Assign a stable anchor id at the original reference location.
- Assign a matching id to the glossary entry and include a backlink to the original location.

Example:

Input pattern:

```text
争点（そうてん）*1
```

Body HTML:

```html
<ruby>争点<rt>そうてん</rt></ruby><a href="#glossary-1" id="ref-1" class="footnote">*1</a>
```

Glossary HTML:

```html
<li id="glossary-1">
  <p>...</p>
  <p><a href="#ref-1" class="backlink">本文へ戻る</a></p>
</li>
```

If the source contains multiple glossary markers, keep the numbering exactly as given.

## Glossary Section Handling

- If the source already has a glossary appendix such as `### 言葉の解説 (Glossary)`, convert it into a semantic HTML section and preserve all entries.
- Render the glossary with an ordered list when the entries are numbered.
- Ensure every glossary entry can link back to the source location.
- Do not invent glossary content that is not present in the source.

## CSS Rules

Embed all CSS inside a single `<style>` tag in the `<head>`. Do not use inline styles or external stylesheets.

Required design baseline:

- `body` font stack: `-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif`
- Soft off-white background such as `#fdfdfd`
- Dark gray text such as `#333`
- Comfortable body `line-height` around `1.6`
- Centered reading column with `max-width: 800px`
- Generous spacing and padding
- Clean, professional, understated styling that prioritizes readability

Required font sizing:

- `h1`: `1.8em`
- `h2`: `1.6em`
- `h3`: `1.4em`
- `p`: `1.2em`
- Furigana text should render at `0.5em`

For ruby sizing, apply the `0.5em` rule to `<rt>` so the kanji text remains readable.

## Design Direction

- Aim for elegant editorial readability, not flashy landing-page aesthetics.
- Use subtle borders, soft shadows, restrained spacing, and quiet color contrast when helpful.
- Make headings clear and scannable.
- Keep glossary links visibly interactive but not distracting.
- Ensure the page works well on both desktop and mobile widths.

## Hard Guardrails

- Preserve 100% of the original content.
- Do not omit, paraphrase, summarize, or rewrite any text.
- Do not drop furigana, glossary entries, lists, or markers.
- Do not add external CSS, external scripts, fonts, or assets.
- Do not use inline `style=""` attributes.
- Do not split output across multiple files.
- Do not break glossary numbering or the reference-link relationship.

## Output Rules

- Return one complete HTML document only.
- Put all CSS inside `<style>` in the document `<head>`.
- Keep the HTML self-contained and downloadable as a single file.
- Use valid semantic HTML wherever possible.

## Quick Verification Checklist

Before finalizing, confirm:

- The output is a complete HTML5 document.
- All original content is present.
- Ruby annotations render with `<ruby>` and `<rt>` when applicable.
- `*n` glossary markers link to the correct appendix entries.
- Glossary entries link back to their original reference points.
- No external dependencies or inline styles were used.

## Example

Input:

```markdown
# 学習メモ

争点（そうてん）*1を整理します。

---

### 言葉の解説 (Glossary)

1. 争点
* **意味 (Meaning):** 議論や検討の中心になるポイント。
```

Output pattern:

```html
<!DOCTYPE html>
<html lang="ja">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>学習メモ</title>
  <style>
    body {
      margin: 0;
      padding: 2rem;
      background: #fdfdfd;
      color: #333;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
      line-height: 1.6;
    }
    main {
      max-width: 800px;
      margin: 0 auto;
    }
    h1 { font-size: 1.8em; }
    h2 { font-size: 1.6em; }
    h3 { font-size: 1.4em; }
    p { font-size: 1.2em; }
    rt { font-size: 0.5em; }
  </style>
</head>
<body>
  <main>
    <article>
      <h1>学習メモ</h1>
      <p><ruby>争点<rt>そうてん</rt></ruby><a href="#glossary-1" id="ref-1" class="footnote">*1</a>を整理します。</p>
      <hr>
      <section aria-labelledby="glossary-title">
        <h3 id="glossary-title">言葉の解説 (Glossary)</h3>
        <ol>
          <li id="glossary-1">
            <p><strong>争点</strong></p>
            <p><strong>意味 (Meaning):</strong> 議論や検討の中心になるポイント。</p>
            <p><a href="#ref-1" class="backlink">本文へ戻る</a></p>
          </li>
        </ol>
      </section>
    </article>
  </main>
</body>
</html>
```
