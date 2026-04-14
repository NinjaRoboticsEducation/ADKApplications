# YTtranscript Project Agent Prompt

Use this workflow whenever the user provides a YouTube or video link and asks for reading material generation.

## Objective

Turn the provided video into a single readable HTML study page for language shadowing learning. Prioritize transcript completeness, timestamp fidelity, and reading clarity over visual decoration.

## Required Workflow

### Step 1: Accept the user request

- Expect the user to provide a YouTube or other video link and ask for reading material generation.
- Confirm the target link and treat that video as the single source of truth for the task.

### Step 2: Generate the full transcript

- Read the provided video.
- Use the `$yttranscript-generator` skill to create a complete transcript for the entire video.
- Prefer the most complete original-language transcript available.
- Preserve timestamps when available.
- Prioritize 100% transcript completeness. If captions are incomplete, use the skill's fallback workflow to obtain a full transcript rather than summarizing or skipping content.

### Step 3: Optimize the transcript structure

- Use the `$yttranscript-optimizer` skill on the transcript produced in Step 2.
- Keep 100% of the original transcript content in the same order.
- Only improve structure:
  - group the transcript into topic-based paragraphs or sections
  - add a short subtitle for each section
  - add key takeaways after the transcript
- Do not rewrite, paraphrase, shorten, translate, or otherwise modify the transcript body.

### Step 4: Produce the first-pass HTML reading material

- Use the `$frontend-design` skill to convert the optimized transcript from Step 3 into a single HTML file in the project root.
- Name the HTML file according to the video's title.
- Sanitize the title for filesystem safety by replacing unsafe filename characters.
- Keep the output as one self-contained HTML file with inline CSS and any minimal inline JavaScript only if needed.
- Prefer transcript cue markup that the next optimization step can refine reliably, especially:
  - `.cue`
  - `.cue-time`
  - `.cue-text`

### Step 5: Refine and optimize the HTML learning material

- Use the `$ythtml-optimizer` skill on the HTML produced in Step 4 together with the original YouTube link.
- Embed the source YouTube video directly into the final page.
- Convert each transcript cue into `<ruby>` markup with the timestamp inside `<rt>`.
- Add playback-aware active-line highlighting and reliable cue synchronization behavior.
- Add interactive dictionary lookup for English words with graceful fallback behavior.
- Include file-mode protection so opening the page as `file://...html` shows localhost preview guidance instead of a broken YouTube error screen.
- When the page is served over HTTP(S), include the recommended YouTube embed identity parameters such as `origin` and `widget_referrer`.
- Review the final HTML for structure, usability, synchronization behavior, readability, and interactive learning quality before marking the task complete.
- If the final HTML is missing reliable cue timestamps or parseable cue structure, fix the Step 4 HTML first instead of faking synchronization.
- Do not sign off on embed playback after testing only from a local file path. Preview the page through localhost or another HTTP(S) origin first.

## Output Requirements

- The final deliverable must be a single HTML file at the project root.
- The page must focus on readability and transcript completeness for language shadowing learning.
- Include the full optimized transcript, including all section subtitles and the key takeaways section.
- Preserve all transcript content from Step 2 inside the transcript portion of the page.
- If timestamps exist, display them clearly and consistently.
- Embed the original YouTube video directly in the page.
- Highlight the currently active subtitle line during playback when synchronization is available.
- Render cue timestamps inside `<rt>` and keep the `<rt>` font size at `0.4em`.
- Provide interactive English word lookup with graceful failure behavior.
- Use typography, spacing, and layout that support long-form reading on both desktop and mobile.
- Avoid clutter, decorative distractions, and layouts that hide or collapse transcript content.
- Do not require a build step for the final HTML to work.
- Keep the page self-contained aside from the required runtime YouTube and dictionary integrations.
- Ensure the local review workflow includes an HTTP preview path for YouTube playback and synchronization.

## Content and Quality Rules

- Never replace the transcript with a summary.
- Never omit repeated phrases, filler words, or uncertain wording that appears in the transcript.
- Never silently correct grammar or spoken-language irregularities inside the transcript.
- Keep summaries separate from the transcript body.
- Favor completeness and legibility over aggressive styling.
- If any required skill is unavailable, report that clearly instead of pretending the workflow succeeded.
- If synchronization cannot be made reliable, say so clearly and fix the HTML instead of simulating accurate behavior.
- Treat YouTube error 153 as an embed-context problem first: check whether the page is being opened from `file://` and whether the embed includes the required identity parameters.

## Suggested HTML Structure

- Video title
- Source link
- Embedded YouTube player
- Optional metadata block for duration and language if available
- Key takeaways section near the top or bottom
- Full transcript sections with subtitles
- Clear timestamp styling when timestamps are present
- Active cue highlighting
- Dictionary popup or floating definition panel

## File Naming

- Save the final file in the project root.
- Use the video title as the base filename.
- Convert spaces to hyphens or underscores.
- Remove characters that are unsafe for filenames.
- Use the `.html` extension.

## Completion Standard

The task is complete only when:

1. A full transcript has been generated from the video.
2. The transcript has been optimized structurally without changing its content.
3. A single HTML file has been created at the project root and named after the video title.
4. The HTML has been refined with embedded playback, synchronized cue highlighting, ruby timestamps, and interactive dictionary support.
5. The HTML has been reviewed under an HTTP(S) preview for structure, usability, synchronization behavior, readability, and interactive learning quality.
