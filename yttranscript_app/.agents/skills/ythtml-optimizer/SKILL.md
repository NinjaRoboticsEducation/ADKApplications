---
name: ythtml-optimizer
description: Refine transcript-heavy HTML into a shadowing-ready YouTube study page with synchronized playback cues, ruby timestamps, and inline dictionary support. Use when Codex has an existing transcript HTML file plus the source YouTube link and needs to upgrade that HTML for language shadowing practice without losing transcript completeness or breaking usability.
---

# ythtml-optimizer

## Quick Start

Use the bundled optimizer on the HTML produced by the earlier transcript workflow:

```bash
python3 scripts/optimize_shadowing_html.py input.html "<youtube-url>" --title "<video-title>"
```

Then validate the result:

```bash
python3 scripts/validate_shadowing_html.py "<video-title>.html" --youtube-url "<youtube-url>"
```

For interactive playback testing, serve the page over localhost instead of opening it with `file://`:

```bash
python3 scripts/serve_shadowing_html.py "<video-title>.html"
```

## Workflow

1. Start from the transcript HTML produced after `$frontend-design`, not from raw transcript text.
2. Preserve transcript completeness while rebuilding the page for shadowing.
3. Add an embedded YouTube player that can be controlled without leaving the page.
4. Convert every timestamped cue into a `<ruby>` structure with the timestamp inside `<rt>`.
5. Add active-line highlighting driven by the embedded video's current playback position.
6. Add click and selection based dictionary lookup for English words.
7. Validate the final HTML for the required shadowing features before delivery.
8. Preview the final page over `http://127.0.0.1` or another HTTP(S) origin before signing off.

## Input Expectations

- Preferred input cue markup:
  - `.cue` wrapper for each cue
  - `.cue-time` element containing `[HH:MM:SS.mmm --> HH:MM:SS.mmm]`
  - `.cue-text` element containing the spoken text
- The bundled optimizer also supports fallbacks such as:
  - `.cue` elements with `data-start` and `data-end`
  - cue text that begins with `[start --> end]`
  - existing section headings and key takeaway lists in HTML
- If the upstream HTML does not contain reliably parseable timestamps, fix Step 4 first instead of guessing timings.

## Non-Negotiable Rules

- Do not delete transcript cues.
- Do not rewrite or summarize transcript lines inside the transcript body.
- Do not remove timestamps.
- Keep the output as a single HTML file with inline CSS and inline JavaScript.
- Use external runtime services only where required for playback and dictionary lookup.
- Fail gracefully when the YouTube API or dictionary API is unavailable.
- Do not treat `file://...html` preview as a valid final embed test because YouTube error 153 is triggered when the request lacks an HTTP referrer.

## Required Output Features

- Embed the original YouTube video directly in the page.
- Highlight the currently active subtitle line during playback.
- Make cues clickable so the learner can jump playback to that line.
- Render cue timestamps inside `<rt>` and set the `<rt>` font size to `0.4em`.
- Keep transcript sections and key takeaways readable on both desktop and mobile.
- Add a floating dictionary popup for English word clicks and selections.
- Cache dictionary lookups and show a clear fallback message when definitions are unavailable.
- Detect local-file preview mode and show localhost preview guidance instead of surfacing a broken YouTube error screen.
- When using the IFrame API, include `origin` and `widget_referrer` whenever the page is served from HTTP(S).

## Tooling

- `scripts/optimize_shadowing_html.py` reads transcript HTML plus a YouTube link and rebuilds the page as a synchronized shadowing document.
- `scripts/serve_shadowing_html.py` serves the generated HTML over localhost so the YouTube embed has an HTTP referrer and the synchronization layer can be tested correctly.
- `scripts/validate_shadowing_html.py` checks the final HTML for the required embed, ruby, synchronization, and dictionary features.
- Read `references/shadowing-html-contract.md` when you need the expected input shapes, output behavior, or validator assumptions.

## Delivery

- Default output file name should still be based on the video title.
- Review the final page for structure, usability, synchronization behavior, readability, and interactive learning quality.
- If validation fails, fix the HTML rather than weakening the checks.
- If the page is being reviewed locally, preview it through localhost before deciding whether the YouTube embed is healthy.
