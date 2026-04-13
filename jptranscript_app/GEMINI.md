# AGENTS.md

## Purpose

This project converts raw Japanese podcast or YouTube transcript text into a refined, learner-friendly HTML document.

When the user provides raw Japanese transcript content directly in chat or uploads a `.txt` file, process it strictly through the workflow below. Do not skip, merge, reorder, or parallelize the transformation steps.

## Required Working Style

- Work streamingly: tell the user which step is currently running and continue through the pipeline without waiting unless blocked.
- Complete and verify one step before starting the next step.
- Treat the output of each step as the only input to the next step.
- Preserve content completeness throughout the workflow.
- Do not summarize, shorten, or drop content unless the active skill explicitly allows it.
- If any step fails or produces uncertain output, fix that step first before moving forward.
- Do not jump ahead to HTML generation or design work before all text-processing steps are complete.

## Input Rules

- Accept either:
  - raw Japanese transcript text pasted by the user
  - an uploaded `.txt` file containing raw Japanese transcript text
- Treat the transcript as the source of truth.
- Preserve speaker labels, ordering, and meaning unless the active skill explicitly transforms presentation.

## Mandatory Sequential Workflow

### Step 1. Transcript Optimization

Use `$jptranscript-optimization`.

Goal:
- Optimize the raw Japanese transcript content.

Requirements:
- Run this step first on the original raw input.
- Produce the Step 1 output content, then pass that exact output to Step 2.

### Step 2. Paragraph Structuring

Use `$jptranscript-paragraph`.

Goal:
- Refine the structure of the Step 1 output content.

Requirements:
- Use only the Step 1 output as input.
- Preserve wording while improving structure.
- Produce the Step 2 output content, then pass that exact output to Step 3.

### Step 3. Full Furigana

Use `$jptranscript-furigana`.

Goal:
- Add furigana reading aids to kanji in the Step 2 output content.

Requirements:
- Use only the Step 2 output as input.
- Produce the Step 3 output content, then pass that exact output to Step 4.

### Step 4. Furigana Refinement

Use `$jptranscript-furigana-refinement`.

Goal:
- Refine the furigana of the Step 3 output content.

Requirements:
- Use only the Step 3 output as input.
- Produce the Step 4 output content, then pass that exact output to Step 5.

### Step 5. Phrase Glossary

Use `$jptranscript-phase-glossary`.

Goal:
- Add clear explanations of difficult Japanese phrases and sentence patterns to the Step 4 output content.

Requirements:
- Use only the Step 4 output as input.
- Preserve the original body except for allowed annotation markers and appendix content defined by the skill.
- Produce the Step 5 output content, then pass that exact output to Step 6.

### Step 6. HTML Generation

Use `$jptranscript-html`.

Goal:
- Convert the Step 5 output content into a well-structured single HTML file.

Requirements:
- Use only the Step 5 output as input.
- Write the final HTML file to the project root.
- Autogenerate the filename from the content topic using a concise kebab-case slug when possible.
- Use the `.html` extension.
- If the topic is unclear, use `jp-transcript-output.html`.
- If a filename already exists, append a numeric suffix instead of overwriting silently.

### Step 7. Readability-Focused Beautification

Use `$frontend-design`.

Goal:
- Beautify the Step 6 HTML with a strong focus on both readability and printability.

Requirements:
- Edit the single HTML file created in Step 6.
- Preserve all existing content, glossary links, ruby, and document structure.
- Improve the visual design without turning it into a flashy marketing page.
- Prioritize reading comfort, clarity, spacing, navigation, and mobile responsiveness.
- For printing, prioritize reading comfort, content focus and best A4 printing setting.

## Verification Rules Between Steps

Before moving from one step to the next, verify that:

- the current step finished successfully
- the output is complete
- the output still preserves the intended content
- the output is valid input for the next step

Minimum step checks:

- After Step 1: transcript is cleaned and still complete in meaning.
- After Step 2: structure is improved and wording is preserved.
- After Step 3: furigana is broadly present where expected.
- After Step 4: furigana clutter is reduced according to the refinement rules.
- After Step 5: glossary markers and glossary appendix are aligned correctly.
- After Step 6: the output is a single complete self-contained HTML file.
- After Step 7: the HTML remains readable, valid, and content-complete.

## Output Rules

- Final deliverable: one refined HTML file at the project root.
- Do not replace the final HTML with Markdown, plain text, or multiple split files.
- Do not omit the glossary appendix, ruby annotations, or glossary backlinks once introduced.
- Intermediate step outputs may be kept in working memory unless the user explicitly asks to save them.

## Skill Reference

Use these exact project-local skills:

- `$jptranscript-optimization`
- `$jptranscript-paragraph`
- `$jptranscript-furigana`
- `$jptranscript-furigana-refinement`
- `$jptranscript-phase-glossary`
- `$jptranscript-html`
- `$frontend-design`

Project-local skill folders are under `.agents/skills/`.

## Strictness Rule

This workflow is mandatory for transcript-to-HTML tasks in this project.

When the task matches this pipeline:

- do not invent an alternative workflow
- do not skip validation between steps
- do not combine multiple text-transformation steps into one
- do not perform design work before the HTML step exists
- do not stop after an intermediate text output when the requested task is a final HTML deliverable
