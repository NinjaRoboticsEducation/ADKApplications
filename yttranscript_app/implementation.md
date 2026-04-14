# YTTranscript App -> Google ADK + Ollama (Gemma 4) Implementation Plan

## 1. Purpose

This document describes how to transform the current `yttranscript_app` workflow from a prompt-and-skill driven process into a runnable local AI agent application built with Google ADK and Ollama using a local Gemma 4 model.

The plan is based on:

- repository root `README.md`
- `jptranscript_app/README.md`
- `jptranscript_app/AGENTS.md`
- `jptranscript_app/agent.py`
- `jptranscript_app/workflow.py`
- `jptranscript_app/implementation.md`
- `yttranscript_app/AGENT.md`
- all skill definitions and bundled scripts under `yttranscript_app/.agents/skills/`

The goal is not to copy `jptranscript_app` mechanically. The goal is to reuse its strongest architectural ideas:

- ADK as the application shell
- a lightweight root agent
- file-backed workflow orchestration
- deterministic processing wherever possible
- explicit, bounded local LLM calls only where language judgment is actually needed

## 2. Current-State Findings

### 2.1 What `yttranscript_app` is today

`yttranscript_app` is currently a workflow specification, not a complete ADK application.

It contains:

- `AGENT.md` with a five-step manual workflow
- four project-local skills:
  - `yttranscript-generator`
  - `yttranscript-optimizer`
  - `frontend-design`
  - `ythtml-optimizer`
- deterministic helper scripts inside the skills for transcript extraction, validation, HTML optimization, and localhost preview

It does not currently contain:

- `yttranscript_app/__init__.py`
- `yttranscript_app/agent.py`
- `yttranscript_app/workflow.py`
- an ADK `root_agent`
- an ADK `app`
- resumable manifest-based execution
- a file-backed stage pipeline comparable to `jptranscript_app`

### 2.2 What the existing workflow already does well

- It has a clear end-to-end product goal: video link -> readable shadowing HTML page.
- It treats transcript completeness as a hard requirement.
- It already has useful deterministic assets:
  - caption/ASR transcript generation
  - transcript integrity validation
  - HTML feature validation
  - localhost preview server for YouTube embed testing
- It clearly separates transcript generation, structuring, first-pass HTML, and HTML enhancement.

### 2.3 What is weak or risky in the current form

- The workflow lives mostly as instructions instead of executable orchestration.
- Critical behavior depends on manual skill invocation rather than application code.
- The `frontend-design` step is too open-ended for a constrained local model and can introduce drift, bloat, or output instability.
- There is no artifact manifest, no resumability, and no stage-level repair strategy.
- There is no ADK-native web app integration yet.
- There is no robust strategy for handling very long Japanese transcripts without overloading the model context.

### 2.4 Reference Output Contract From `ai-agent-design-patterns.html`

The file `yttranscript_app/Output/ai-agent-design-patterns.html` should be treated as the reference output contract for the new app.

The final generated HTML does not need to be byte-identical, but it should be structurally equivalent in the areas that matter for the user experience:

- a single self-contained HTML file
- a hero/header area with title and source metadata
- a sticky player/control panel beside the transcript on desktop
- a `runtime-warning` area for file-mode and embed failures
- a `takeaways` block
- one or more `transcript-section` blocks
- per-cue clickable transcript rows using `.cue`
- per-cue timing data stored in `data-start` and `data-end`
- transcript text rendered inside `<ruby>` with timestamp text in `<rt>`
- active cue highlighting
- dictionary popup UI and `.dict-word` spans
- responsive layout that collapses cleanly on smaller screens

This reference output should be used to drive:

- DOM contract tests
- CSS selector stability
- accessibility checks
- final snapshot review during QA

### 2.5 Vulnerability And Robustness Findings

Reviewing the current helper scripts and the existing plan surfaces several concrete risks that the refined build must address:

1. **Unbounded external process runtime**
   The transcript generator uses `subprocess.run(...)` without a timeout. `yt-dlp` and Whisper can hang indefinitely on bad inputs, network stalls, or extractor changes.

2. **Unbounded network reads**
   Subtitle track downloads currently use `urllib.request.urlopen(...)` without an explicit timeout or maximum response size guard.

3. **Input host expansion risk**
   The current plan says “validate the URL,” but it does not yet require a strict allowlist for YouTube hosts. The app objective is explicitly YouTube-link driven, so the safest design is YouTube-only input canonicalization.

4. **Prompt injection through transcript content**
   Transcript text is untrusted content. If fed into Gemma 4 loosely, a transcript containing instruction-like text can distort the structuring stage.

5. **HTML / DOM injection risk in the current shadowing HTML helper**
   The existing optimizer script uses `innerHTML` in several places. Most transcript content is escaped on the Python side, but third-party dictionary payloads are still rendered as HTML strings in the browser, which is a real XSS-shaped risk.

6. **Third-party runtime fragility**
   Final pages depend on:
   - YouTube iframe runtime
   - dictionaryapi.dev
   - local browser referrer behavior

   These dependencies must degrade gracefully without breaking the transcript page itself.

7. **Missing explicit supply-chain and dependency checks**
   The current plan mentions tests and linting, but not dependency auditing, version pinning checks, or security scanning for new packages and CLI tools.

8. **Insufficient output-contract testing**
   The current plan validates transcript integrity and shadowing HTML features, but it does not yet explicitly compare generated output against the provided example HTML contract.

## 3. Recommended Agentic Design Pattern

## Recommendation

Use a **custom sequential orchestrator agent with stage-local repair loops**.

In practical terms:

- the top-level ADK layer should be a lightweight custom root agent, similar to `jptranscript_app`
- the main workflow should run in a deterministic `workflow.py`
- each stage should write artifacts to disk
- only LLM-dependent stages should call Gemma 4
- each LLM-dependent stage should use bounded chunk processing plus validator-driven retries

## Why this is the best fit

This is the closest match to the real needs of `yttranscript_app`:

- The workflow is inherently sequential. Transcript extraction must happen before structuring. Structuring must happen before HTML rendering. HTML rendering must happen before shadowing enhancement.
- A plain `SequentialAgent` is not enough by itself because this app needs artifact paths, manifest updates, deterministic scripts, and chunk-local retries.
- A full multi-agent team would add context overhead and coordination cost that is hard to justify on local Gemma 4.
- A pure `LoopAgent` is also not the right top-level pattern because the whole product is not iterative by default. Only specific repair points are iterative.

## Final pattern choice

- **Primary pattern:** sequential pipeline
- **Implementation style:** custom ADK orchestrator instead of pure `SequentialAgent`
- **Secondary pattern:** loop-style repair for failing chunks or failing stage validators

This is also consistent with the `jptranscript_app` direction: use ADK for app integration and user interaction, but keep long-running artifact-aware control flow in custom code.

## 4. Target Architecture

## 4.1 Proposed package layout

```text
yttranscript_app/
├── __init__.py
├── agent.py
├── workflow.py
├── fixtures/
│   ├── html_reference/
│   │   └── ai-agent-design-patterns.html
│   ├── transcript_samples/
│   └── metadata_samples/
├── prompts/
│   ├── structure_transcript.md
│   └── refine_takeaways.md
├── tools/
│   ├── ollama_client.py
│   ├── youtube_transcript.py
│   ├── transcript_structure.py
│   ├── html_renderer.py
│   ├── shadowing_html.py
│   ├── serve_shadowing_html.py
│   └── job_state.py
├── templates/
│   └── shadowing_style.css
├── tests/
├── Output/
├── Work/
└── legacy_skills/
    └── ... archived copies of the current `.agents/skills` content
```

## 4.2 ADK-facing layer

`agent.py` should define:

- `root_agent`
- `app`

and use the same discovery conventions the ADK expects:

- `yttranscript_app/__init__.py` must contain `from . import agent`
- `agent.py` must expose either `root_agent` or `app`

Recommended structure:

- `root_agent`: a custom ADK `BaseAgent`
- `app`: `App(name="yttranscript_app", root_agent=root_agent, resumability_config=...)`

## 4.3 Workflow layer

`workflow.py` should own:

- input resolution
- job id creation
- stage manifest creation
- per-stage execution
- stage artifact writing
- chunk-level retry logic
- validation
- final output path selection

The root agent should not hold full transcripts in session state. It should only hold compact metadata such as:

- `last_job_id`
- `last_stage`
- `last_output_path`
- `last_manifest_path`
- `last_status`

## 4.4 LLM invocation layer

Follow the `jptranscript_app` pattern:

- use a small explicit Ollama chat client for heavy workflow calls
- keep prompts stage-specific
- send only chunk-sized payloads
- set low temperature
- enable `keep_alive`
- log retries and validation outcomes per chunk

Recommended default model target:

- `gemma4-agent` if the custom Ollama profile already exists
- otherwise `gemma4:26b` on 32 GB systems
- otherwise `gemma4:4b` with stricter chunking and more deterministic fallbacks

If later ADK sub-agents are added for smaller tasks, use:

- `LiteLlm(model="ollama_chat/gemma4-agent")`

and never the `ollama/` prefix.

## 5. Proposed End-to-End Workflow

## Stage 0. Request ingestion and job setup

Input:

- YouTube link
- optional spoken language hint
- optional output title override

Responsibilities:

- validate the URL
- enforce a strict YouTube host allowlist (`youtube.com`, `www.youtube.com`, `m.youtube.com`, `youtu.be`)
- canonicalize the user input down to a single normalized video id plus canonical source URL
- reject unsupported URL shapes early instead of letting downstream tools guess
- keep output filenames app-controlled; do not accept arbitrary file output paths from chat input
- create a job id
- create `Work/<job-id>/`
- initialize manifest
- store input metadata

No LLM is needed.

## Stage 1. Transcript acquisition

Driver:

- deterministic Python tool wrapping the existing `generate_transcript.py`

Responsibilities:

- inspect the video with `yt-dlp`
- prefer human subtitles
- fall back to automatic subtitles when needed
- reject incomplete coverage
- optionally fall back to full-audio ASR
- emit a normalized transcript artifact
- enforce subprocess timeouts and clear retry budgets
- enforce download timeouts and maximum caption payload size
- preflight required tools (`yt-dlp`, `ffmpeg`, Whisper when needed) before long work starts
- store transcript source diagnostics in the manifest, including:
  - extractor used
  - language
  - duration
  - coverage report
  - whether ASR fallback was triggered

Primary output:

- `stage1_transcript.txt`

Validation:

- first cue near start
- last cue near duration end
- coverage >= 98%
- no unexplained long gaps

No Gemma call is required here.

## Stage 2. Transcript structuring

Driver:

- Gemma 4 chunk workers plus deterministic validator

Responsibilities:

- preserve the transcript body verbatim
- group transcript into topic-based sections
- add short section subtitles
- produce a separate `Key Takeaways` section
- treat transcript content as data, not instructions
- wrap transcript chunks in explicit delimiters and state that content inside those delimiters must never be interpreted as instructions
- use structured output where possible so the model returns a schema-backed representation of:
  - section title
  - section body
  - optional takeaway bullets

Primary output:

- `stage2_structured.md`

Validation:

- transcript body remains intact after normalization and structure marker removal
- timestamps remain preserved
- at least one section heading exists
- takeaways remain separate from the transcript body
- schema validation passes before reducer merge
- prompt-injection regression fixtures pass

This is the main LLM-dependent stage.

## Stage 3. Deterministic HTML skeleton rendering

Driver:

- deterministic Python renderer

Responsibilities:

- convert structured transcript into semantic HTML
- keep cue-level markup parseable for the next stage
- emit stable CSS hooks such as:
  - `.cue`
  - `.cue-time`
  - `.cue-text`
- include title, source link, section blocks, transcript cues, and takeaways
- mirror the reference output contract from `ai-agent-design-patterns.html`
- HTML-escape all transcript-derived text and attribute values
- generate predictable DOM ids and class names so the optimizer and validator do not depend on brittle inference

Primary output:

- `stage3_base.html`

This stage should replace the current open-ended `frontend-design` dependency for the core layout.

## Stage 4. Shadowing enhancement

Driver:

- deterministic Python tool wrapping the existing `optimize_shadowing_html.py`

Responsibilities:

- embed YouTube playback
- convert timestamped cues into `<ruby>` with `<rt>`
- add click-to-seek behavior
- add active cue highlighting
- add dictionary lookup with graceful fallback
- add `file://` preview warning
- add `origin` and `widget_referrer` handling for HTTP(S) preview
- add explicit `referrer` and CSP strategy suitable for a self-contained page
- render third-party dictionary responses with DOM-safe text node insertion instead of concatenated HTML strings
- fail closed for untrusted HTML rather than rendering raw response content
- preserve a usable transcript-only experience when external services fail

Primary output:

- `stage4_shadowing.html`

Validation:

- run `validate_shadowing_html.py`
- manually preview via localhost when possible
- run DOM contract checks against the reference HTML
- verify CSP / referrer behavior does not break the YouTube embed under localhost

## Stage 5. Final save and report

Driver:

- deterministic Python save step

Responsibilities:

- save into `yttranscript_app/Output/`
- avoid silent overwrites
- write manifest completion state
- report final output and any warnings
- save a final QA summary alongside the manifest, including validator pass/fail data and any degraded-mode warnings

Primary output:

- final user-facing HTML file

## 6. Skill-to-Agent Component Mapping

| Existing asset | Current role | Proposed ADK-era role | LLM needed? | Notes |
|:---|:---|:---|:---|:---|
| `yttranscript_app/AGENT.md` | Human-readable workflow contract | Root orchestrator contract and acceptance criteria source | No | Convert into executable workflow logic and tests |
| `yttranscript-generator` | Transcript extraction skill | `generate_transcript_stage()` tool wrapper | No | Reuse current script and completeness policy almost as-is |
| `yttranscript-optimizer` | Structural transcript skill | `structure_transcript_stage()` Gemma chunk worker | Yes | Keep validator-driven preservation rules |
| `frontend-design` | LLM-first HTML creation | `render_base_shadowing_html()` deterministic renderer + style template | Usually no | Keep design intent, remove large-model dependence from critical path |
| `ythtml-optimizer` | HTML enhancement skill | `optimize_shadowing_html_stage()` tool wrapper | No | Reuse current optimizer, validator, and localhost preview flow |
| `validate_transcript_integrity.py` | Transcript body preservation checker | Stage 2 hard gate | No | Must become part of automated pipeline execution |
| `validate_shadowing_html.py` | HTML feature checker | Stage 4 hard gate | No | Required before final success |
| `serve_shadowing_html.py` | Manual localhost preview | Developer QA helper and optional final message hint | No | Keep outside model path |

## 7. Step-by-Step Transformation Strategy

1. Create the ADK package shell for `yttranscript_app`.
   Add `__init__.py`, `agent.py`, and `workflow.py`.

2. Move the current `.agents/skills` folder into a clearly labeled legacy reference area.
   Keep it available during migration, but stop treating it as the runtime system.

3. Implement the custom root ADK agent.
   Match the `jptranscript_app` pattern: receive user input, start the workflow in a background thread, stream progress events, and return a compact final summary.

4. Add manifest-based job execution.
   Create `Work/<job-id>/manifest.json` and stage artifact paths before any heavy processing begins.

5. Port transcript generation into a deterministic stage wrapper.
   Reuse `generate_transcript.py`, expose structured stage results, and report transcript coverage diagnostics in the manifest.

6. Implement Gemma-backed transcript structuring as the only mandatory LLM-heavy stage.
   Add prompt files, bounded chunking, a reducer, and integrity validation.

7. Replace the current free-form `frontend-design` stage with deterministic HTML rendering.
   Build the first-pass HTML from the validated structured transcript, not from a fresh generative HTML prompt.

8. Port shadowing enhancement into a deterministic HTML optimization stage.
   Reuse `optimize_shadowing_html.py`, `validate_shadowing_html.py`, and `serve_shadowing_html.py`.

9. Add stage-specific retry and repair logic.
   Retry only failing chunks or the failing stage, never the whole job by default.

10. Add automated tests.
    Include transcript completeness checks, transcript integrity checks, HTML validation checks, DOM contract checks against the provided example HTML, and at least one long-form fixture regression.

11. Add ADK web integration and documentation.
    Make sure the app is discoverable by `adk web`, explain the local Ollama dependency, and document localhost preview for the final HTML.

12. Add security hardening before declaring parity.
    Add host allowlists, path-rooting, timeouts, safe DOM rendering, dependency auditing, and prompt-injection regression tests.

13. Remove the old workflow dependency once parity is reached.
    After the new app reproduces the required behavior, archive the legacy prompt-only workflow and keep only the reusable scripts and reference docs.

## 8. Long Japanese Text Strategy for Gemma 4

## 8.1 Core rule

Do not treat long Japanese transcript text as chat state.

Store large artifacts on disk and only pass bounded slices into the model.

## 8.2 Required processing pattern

Use **Map -> Reduce -> Repair** for every LLM-dependent long-text stage.

### Map

- split the transcript into bounded chunks
- process each chunk independently
- keep overlap context separate from final output

### Reduce

- merge chunk outputs deterministically
- rebuild global headings and takeaways only after chunk outputs are stable

### Repair

- rerun only failing chunks
- if a reducer fails, rerun only the reducer or rebuild the affected section set

## 8.3 Recommended chunking rules for Japanese transcript structure

Use stage-specific chunking, not one generic splitter.

Preferred split points:

1. section boundaries already inferred from cues
2. speaker turns
3. paragraph breaks
4. sentence-ending punctuation such as `。`, `！`, `？`
5. emergency hard split only if no safe boundary exists

Avoid splitting:

- inside timestamps
- inside cue lines
- inside ruby markup
- inside section headings
- inside glossary markers

## 8.4 Recommended starting chunk budget

Start conservatively and benchmark locally:

- transcript structuring chunk size: roughly 1200 to 1600 characters
- overlap: roughly 100 to 150 characters
- reduce chunk size automatically on validation failure or timeout

Use the actual local machine behavior, not the model’s theoretical maximum context window, as the real tuning source.

For very long transcripts:

- checkpoint after each successful chunk batch
- cap the number of retry rounds per chunk
- split multi-hour transcripts into higher-level passes if manifest size or reducer complexity becomes unstable

## 8.5 Context management rules

- keep only small metadata in ADK state
- keep full transcript artifacts on disk
- send only:
  - stage prompt
  - current chunk
  - optional short overlap context
  - optional small section summary
- never inject the full prior document into the model instruction field

## 8.6 Summarization policy

Use summarization only as a supporting layer, never as a replacement for transcript content.

Allowed:

- section subtitles
- key takeaways
- compact reducer hints

Forbidden:

- replacing transcript blocks with summaries
- compressing repeated phrases
- normalizing spoken grammar into written prose
- dropping fillers or false starts when they are part of the transcript

## 8.7 Iterative refinement policy

The model should not do open-ended “improve until good” loops on the entire document.

Instead:

- validator fails
- identify failing chunk or failing reducer
- rerun that specific scope with tighter instructions
- record retry count in the manifest
- fall back to deterministic minimal structure if the LLM remains unstable

## 9. Error Handling and Validation

## 9.1 Failure scopes

Use three failure levels:

- chunk-local
- stage-level
- job-level

## 9.2 Chunk-local failures

Examples:

- Ollama timeout
- malformed heading output
- transcript preservation validator failure

Recovery:

- retry once with the same chunk
- retry again with a smaller chunk size
- fall back to deterministic minimal structure if needed

## 9.3 Stage-level failures

Examples:

- reducer cannot rebuild a clean transcript structure
- HTML enhancement validator fails

Recovery:

- rerun only the failing stage
- reuse upstream stage artifacts
- do not regenerate the transcript unless Stage 1 itself failed

## 9.4 Job-level failures

Examples:

- Ollama unavailable
- `yt-dlp` missing
- Whisper missing when transcript completeness requires ASR fallback
- output directory not writable

Recovery:

- stop cleanly
- preserve intermediate artifacts
- give an actionable user-facing error

## 9.5 Validator checklist

### Transcript generation

- first cue starts near real audio start
- final cue reaches near video duration
- coverage threshold passes
- unexplained long gaps are rejected

### Transcript structuring

- transcript body remains unchanged after removing structural markers
- timestamps remain present and ordered
- headings exist
- key takeaways remain separate

### HTML enhancement

- YouTube embed markers exist
- cue elements include start and end timing
- `<ruby>` and `<rt>` are present
- `<rt>` font size is `0.4em`
- active cue logic exists
- dictionary lookup markers exist
- file-mode guard exists
- `origin` and `widget_referrer` handling exists

### Security hardening

- input URL host allowlist passes
- canonical video id extraction passes
- output path remains inside app-controlled directories
- subprocess timeouts are configured
- network timeouts are configured
- dictionary popup rendering avoids unsanitized `innerHTML` from third-party data
- transcript-derived content is escaped before HTML insertion
- CSP/referrer meta strategy is present and tested

### Output contract against the provided example HTML

- hero/header region exists
- sticky player panel exists on desktop widths
- `.takeaways`, `.transcript-section`, `.cue`, `.dictionary-popup`, and `.runtime-warning` are present
- cues expose `data-start` and `data-end`
- generated page preserves the same core user interaction model as the sample output

## 10. ADK Web Integration Plan

## 10.1 Required runtime setup

At minimum:

- Ollama running locally
- Gemma 4 model available locally
- `OLLAMA_API_BASE="http://localhost:11434"`
- Python 3.10+ environment

Recommended supporting tools:

- `yt-dlp`
- `ffmpeg`
- Whisper or compatible ASR CLI for fallback transcription

## 10.2 ADK wiring

Implementation should mirror the discoverability rules already documented in the repository:

- `yttranscript_app/__init__.py` imports `agent`
- `yttranscript_app/agent.py` exposes `root_agent` and preferably `app`
- the root agent streams progress while `workflow.py` runs in the background
- `App(..., resumability_config=ResumabilityConfig(is_resumable=True))` should be enabled

`adk web` should be treated as the local development interface for this project, not as a production deployment target.

## 10.3 Recommended developer workflow

From the repository root:

```bash
source .venv/bin/activate
adk web .
```

Then:

- open the local ADK web UI
- choose `yttranscript_app`
- submit a YouTube URL
- watch stage progress stream in chat
- inspect `Work/<job-id>/` if a stage fails

Recommended optional commands:

```bash
adk run yttranscript_app
python yttranscript_app/tools/serve_shadowing_html.py "<final-html>"
adk eval yttranscript_app tests/evals/structuring.evalset.json
```

## 10.4 User-facing progress model

The ADK chat should stream messages such as:

- transcript extraction started
- subtitles incomplete, ASR fallback running
- transcript structuring chunk 2/5 completed
- HTML enhancement validation passed
- final output saved to `Output/...html`

This makes long local execution feel alive instead of frozen.

## 11. Major Design Decisions and Reasoning

### Decision 1. Keep ADK as the app shell, not the whole execution engine

Reason:

- ADK is excellent for session management, UI integration, and streaming progress
- the heavy workload here is artifact-driven and stageful
- `jptranscript_app` already proves that this split is practical

### Decision 2. Limit Gemma 4 use to transcript structuring

Reason:

- transcript extraction is better handled by `yt-dlp` plus ASR tooling
- HTML building and shadowing enhancements are already represented by deterministic scripts
- this reduces risk, improves repeatability, and preserves transcript completeness

### Decision 3. Replace free-form HTML generation with deterministic rendering

Reason:

- local LLMs are much more likely to damage transcript fidelity or produce unstable markup during large HTML generation
- the current `ythtml-optimizer` script already expects structured cue markup
- deterministic rendering gives the optimizer a stable upstream contract

### Decision 4. Use file-backed manifests and stage artifacts

Reason:

- this is the only scalable way to handle long transcripts locally
- it enables retries, resumability, debugging, and output audits
- it matches the strongest pattern already used in `jptranscript_app`

### Decision 5. Use loop behavior only for repairs, not as the main pipeline shape

Reason:

- the business flow is ordered, not exploratory
- repair loops are valuable, but only at bounded failure points
- a top-level loop would add complexity without product benefit

### Decision 6. Treat the provided sample HTML as a contract, not just inspiration

Reason:

- the user objective is a specific shadowing-material experience, not merely “some valid HTML”
- contract-driven DOM tests are more reliable than vague aesthetic checks
- this reduces drift when deterministic renderers and validators evolve

### Decision 7. Prefer security-by-default over permissive convenience

Reason:

- the app combines untrusted transcript text, third-party downloads, local subprocesses, and browser-executed HTML
- the safest design is to narrow accepted inputs, root all outputs, use explicit timeouts, and avoid unsafe DOM insertion patterns

## 12. Implementation Roadmap

## 12.1 Shared quality gate for every phase

Every phase should pass these baseline checks before moving forward:

```bash
ruff check yttranscript_app
python -m compileall yttranscript_app
pytest -q
```

Recommended additions to the dev toolchain:

```bash
bandit -r yttranscript_app
pip-audit
```

If Phase 3 or later changes the ADK package boundary, also run:

```bash
python -c "from yttranscript_app.agent import app, root_agent; print(app.name, root_agent.name)"
```

## Phase 1. Scaffold the ADK app

- create package files
- add root agent
- add manifest helpers
- verify `adk web .` discovers `yttranscript_app`

Build gate:

- `ruff check yttranscript_app`
- `python -m compileall yttranscript_app`
- import smoke test for `root_agent` and `app`
- manual `adk web .` discovery check
- manifest schema test with `pytest`

## Phase 2. Port deterministic transcript generation

- wrap `generate_transcript.py`
- emit manifest metadata
- expose completeness failures clearly
- add YouTube host allowlist and canonicalization
- add subprocess and network timeouts
- add tool preflight checks

Build gate:

- unit tests for URL allowlist and canonical video-id extraction
- unit tests for filename sanitization and rooted output paths
- mocked timeout/error tests for `yt-dlp`, `urllib`, and Whisper fallback
- transcript coverage validator tests with saved metadata/caption fixtures
- `bandit -r yttranscript_app`

## Phase 3. Build Gemma-backed transcript structuring

- add prompt files
- add chunking and reducer logic
- wire in integrity validation
- add structured-output schema for section results
- add prompt-injection regression fixtures

Build gate:

- transcript integrity validator passes on golden fixtures
- chunk reducer tests pass
- schema validation tests pass
- `adk eval` runs on a small structuring eval set
- retry/fallback behavior is covered by `pytest`

## Phase 4. Replace `frontend-design` with deterministic HTML rendering

- build stable transcript-to-HTML conversion
- preserve cue markers for the optimizer
- align DOM structure with `Output/ai-agent-design-patterns.html`

Build gate:

- HTML renderer unit tests pass
- DOM contract tests pass against the reference output
- transcript text remains escaped in rendered HTML
- snapshot-style checks confirm required classes and regions exist

## Phase 5. Port shadowing enhancement and validation

- wrap the optimizer
- wrap HTML validator
- preserve localhost preview helper
- remove unsafe third-party `innerHTML` rendering patterns
- add referrer/CSP strategy and localhost playback smoke checks

Build gate:

- `validate_shadowing_html.py` passes
- dictionary popup tests verify DOM-safe rendering
- file-mode guidance tests pass
- localhost preview smoke check passes
- manual browser QA confirms sticky panel, active cue highlighting, and click-to-seek behavior

## Phase 6. Harden, test, and archive legacy flow

- add regression tests
- test long Japanese input behavior
- document local setup and debugging flow
- archive prompt-only legacy runtime instructions

Build gate:

- end-to-end fixture run produces a valid final HTML page
- final DOM contract check passes against the sample output
- dependency audit passes
- QA summary is written into the manifest
- user flow smoke test passes: ADK web chat -> URL input -> final HTML output

## 13. Research Resources

These primary resources should be treated as implementation references while building and hardening the app:

- Google ADK Python quickstart and runtime conventions:
  [https://adk.dev/get-started/python/](https://adk.dev/get-started/python/)
- Google ADK workflow agent concepts and evaluation tooling:
  [https://google.github.io/adk-docs/](https://google.github.io/adk-docs/)
- Ollama context-length guidance for agent workloads:
  [https://docs.ollama.com/context-length](https://docs.ollama.com/context-length)
- Ollama structured outputs for schema-backed responses:
  [https://docs.ollama.com/capabilities/structured-outputs](https://docs.ollama.com/capabilities/structured-outputs)
- YouTube embedded player parameters, including `origin` and `widget_referrer`:
  [https://developers.google.com/youtube/player_parameters](https://developers.google.com/youtube/player_parameters)
- OWASP CSP guidance for static or semi-static HTML pages:
  [https://cheatsheetseries.owasp.org/cheatsheets/Content_Security_Policy_Cheat_Sheet.html](https://cheatsheetseries.owasp.org/cheatsheets/Content_Security_Policy_Cheat_Sheet.html)

These resources support several specific changes in this plan:

- using `adk web` strictly as a development/debugging surface
- using schema-backed outputs for the Gemma structuring stage
- tuning Ollama context size pragmatically instead of relying on theoretical maximums
- hardening YouTube embed identity parameters
- adding CSP and safer browser-side rendering behavior

## 14. Final Recommendation

The best transformation path is:

- keep the existing product goal
- keep the current deterministic transcript and HTML scripts
- replace the prompt-only runtime with a real ADK app
- use Gemma 4 only where structure and language judgment are genuinely needed
- follow the `jptranscript_app` architecture rather than a generic all-LLM multi-agent design

This produces a system that is:

- local-first
- scalable for long transcripts
- easier to debug
- safer for transcript completeness
- better aligned with constrained local compute
