# JP Transcript ADK — Product Requirements Document (PRD)

> **Status**: Active PRD for all future development  
> **Last Updated**: April 14, 2026  
> **Product**: `jptranscript_app`  
> **Primary Goal**: Reliably convert long Japanese transcript content into learner-friendly HTML on a local machine using Google ADK and a local Gemma model.

---

## 1. Document Purpose

This document is the canonical Product Requirements Document for `jptranscript_app`.

It replaces the earlier implementation plan where needed and incorporates:

- the original product intent
- the current code audit findings
- the runtime limitations observed on the local machine
- updated platform guidance for Google ADK, Ollama, and Gemma

Future development should treat this document as the source of truth for:

- system architecture
- workflow design
- error handling
- performance expectations
- testing scope
- phased implementation priorities

If existing code or older notes conflict with this PRD, this PRD wins.

---

## 2. Product Goal

`jptranscript_app` must transform raw Japanese transcript content into a polished, learner-friendly HTML document while running locally on consumer hardware.

The system must handle:

- pasted Japanese transcript text
- local `.txt` transcript files
- long-form content that exceeds the safe prompt budget of a single local model call

The output must remain:

- content-complete
- structurally readable
- furigana-enhanced
- glossary-linked
- printable
- safe to render in a browser

---

## 3. Product Context

### 3.1 Existing User Value

The existing workflow aims to turn raw podcast or YouTube transcripts into a single self-contained study document by applying seven sequential transformations:

1. Optimization
2. Paragraph structuring
3. Full furigana
4. Furigana refinement
5. Phrase glossary
6. HTML generation
7. Beautification

That product direction is still correct.

### 3.2 Why the Current Build Is Not Robust Enough

The current codebase passes its small unit tests, but the architecture is not safe for long inputs. The key issue is that the present design sends large intermediate outputs back through `LlmAgent` instructions, which defeats the intended chunking strategy and wastes scarce local context budget.

As a result, the current build is not yet a reliable long-transcript processor. It is a prototype that demonstrates components, not a production-ready local pipeline.

---

## 4. Scope

### 4.1 In Scope

- End-to-end local transcript processing
- Google ADK-based orchestration
- Ollama-hosted Gemma model calls
- Robust long-text chunking and recomposition
- Deterministic processing where LLMs are unnecessary
- Intermediate artifact persistence and resumability
- HTML safety and rendering correctness
- Local performance optimization for limited memory and compute

### 4.2 Out of Scope

- Cloud inference as a primary execution path
- Multi-user server deployment
- OCR, audio transcription, or subtitle extraction
- Full CMS or database-backed content management
- Fancy generative design exploration for the final HTML

The product is a local-first transcript transformation tool, not a general document platform.

---

## 5. Source Inputs and Documentation Assumptions

The current project contains:

- app implementation notes in [implementation.md](./implementation.md)
- a repo-level setup guide in [../README.md](../README.md)

Important note:

- `jptranscript_app/README.md` does not currently exist.
- Until one is added, the repo root `README.md` should be treated as the setup and platform reference for this app.

This PRD assumes future documentation cleanup may add an app-local README, but that is not a blocker for implementation.

---

## 6. Target Users and Use Cases

### 6.1 Primary User

A single developer or learner running the app locally on a Mac workstation, typically pasting or loading Japanese transcript text and expecting a finished HTML study document.

### 6.2 Primary Use Cases

1. Paste a short Japanese transcript and receive an HTML study document.
2. Load a long transcript file and process it without manual splitting.
3. Preserve speaker turns and meaning while improving readability.
4. Add furigana and glossary support for intermediate learners.
5. Save a print-friendly HTML file for later study.

### 6.3 Non-Functional User Expectation

The user should not need to understand chunking, state management, or model limits. Long content must “just work,” or fail clearly with resumable recovery.

---

## 7. Product Success Criteria

The product is considered successful when all of the following are true:

### 7.1 Functional Success

- The system accepts pasted text and `.txt` file input.
- The system completes all seven transformation stages in order.
- The final output is a single valid HTML file.
- Long transcripts are processed without manual user chunking.

### 7.2 Content Quality Success

- Base transcript meaning is preserved.
- Speaker labels are preserved where present.
- Structural formatting improves readability without deleting content.
- Furigana is broadly correct and refinement reduces clutter.
- Glossary markers match glossary entries.
- HTML links and backlinks are valid.

### 7.3 Reliability Success

- A failed chunk does not force the entire job to restart.
- Deterministic stages do not depend on LLM behavior.
- Long inputs do not overflow model context before chunking occurs.
- Invalid HTML or unsafe HTML is not produced silently.

### 7.4 Performance Success

On the target local machine, the app should process a typical long transcript without freezing the machine or exhausting GPU memory.

Exact benchmark targets will be validated later, but the design must prioritize:

- bounded memory growth
- resumable chunk processing
- no unnecessary full-document LLM passes

---

## 8. Constraints

### 8.1 Hardware Constraint

Target machine:

- Apple M2 Max
- 32 GB RAM

The product must be designed for limited local resources. Large-context inference is possible, but expensive.

### 8.2 Model Constraint

The active local model is Gemma via Ollama.

Observed local state:

- `gemma4-agent` is available locally
- current active context allocation observed in `ollama ps`: `8192`

Important platform facts gathered during research:

- Ollama documentation recommends at least `64000` tokens for tasks like agents, coding tools, and web-search-style workloads.
- Ollama documentation also shows context length should be tuned based on available VRAM and verified with `ollama ps`.
- Ollama’s `gemma4:26b` library page advertises a `256K` maximum context window.
- Gemma 4 official product pages emphasize function calling and agentic workflows.

This means:

- large context is available in theory
- large context is not free in practice
- architecture must not rely on “just increase context” as the main fix

### 8.3 Framework Constraint

Google ADK supports:

- workflow agents
- app-level state management
- `output_key`
- App-level features such as context caching, context compression, and resumability

However, ADK state templating injects state values into agent instructions. If large transcript bodies are stored in session state and referenced in instructions, long content can still overflow the model context before any tool call happens.

This is a critical design constraint for this product.

### 8.4 Runtime Constraint

The legacy local Python environment was `3.9.6`, which caused unsupported-version warnings in current ADK dependencies.

The supported runtime baseline for this product is now:

- Python `3.10+`
- verified locally on Python `3.12.12`

Future development must preserve Python `3.10+` compatibility. Falling back to Python `3.9` is out of scope.

---

## 9. Current-State Audit Summary

The existing code audit found the following product-level problems.

### 9.1 Architectural Problems

1. The current chunking strategy is neutralized by state templating because long intermediate outputs are injected into `LlmAgent` instructions.
2. Deterministic stages still use `LlmAgent`, forcing unnecessary model calls on large payloads.
3. The system stores and forwards full text where it should store references or small summaries.

### 9.2 Correctness Problems

1. `refine_furigana()` uses a regex that captures surrounding sentence text instead of only the annotated token in many real cases.
2. `process_text_chunks()` injects chunk labels like `[Processing chunk X of Y]` into model input, and those labels can leak into final output.
3. The documented overlap strategy is not implemented even though an overlap constant exists.
4. `validate_glossary()` can pass malformed glossary sections missing required fields.
5. The TOC HTML conversion can leave `<nav>` unclosed.

### 9.3 Safety Problems

1. HTML generation does not properly escape arbitrary transcript content before embedding it in HTML.
2. File reading accepts path traversal such as `../`.
3. Error strings are returned as if they were valid content instead of using explicit failure paths.

### 9.4 Product Mismatch Problems

1. Documentation and implementation disagree on output location.
2. The scratch end-to-end script is broken.
3. The existing tests are too narrow and do not cover long-content behavior or browser safety.

This PRD is written to correct those failures directly.

---

## 10. Product Principles

All future work must follow these principles.

### 10.1 Principle: Do Not Send Whole Documents to the Model Unless Strictly Necessary

Large transcript bodies must not be injected into agent instructions for convenience.

Instead:

- keep large text in artifacts or working files
- store only references and metadata in state
- pass chunk-sized text into LLM calls deliberately

### 10.2 Principle: Use Deterministic Code for Deterministic Tasks

If a task can be reliably solved in Python, do not route it through Gemma.

This applies especially to:

- furigana refinement
- HTML conversion
- HTML beautification
- validation
- chunk bookkeeping
- file persistence

### 10.3 Principle: Prefer Hierarchical Processing Over Giant Single Passes

Long documents must be processed using:

- map steps on bounded chunks
- reduce steps for global consistency
- repair passes only where validation indicates a problem

### 10.4 Principle: Fail Chunk-Local, Recover Globally

One failed chunk must not invalidate the entire job.

### 10.5 Principle: Preserve Content, Add Structure

The product should enhance readability and learning support without silently deleting transcript meaning.

---

## 11. Target System Architecture

## 11.1 High-Level Architecture

The target product will use:

- **Google ADK App** as the application container
- **a custom orchestrator agent** or equivalent dynamic workflow control
- **chunk workers** for LLM-dependent stages
- **pure Python processors** for deterministic stages
- **artifact-backed intermediate outputs**
- **validator and repair loops** that operate on chunk outputs, not full raw transcript injections

### 11.2 Required Architectural Change

The current `SequentialAgent` plus `LlmAgent` chain is not sufficient for robust long-document handling because:

- it encourages full state templating into prompts
- it uses the model even for tool-only behavior
- it lacks explicit artifact-aware orchestration

Therefore, the next production architecture must use a **custom ADK orchestration layer** for stage control.

### 11.3 App-Level Requirements

The product should define an ADK `App`, not just a root agent, so future builds can use:

- resumability
- app-level configuration
- event compaction or context compression where appropriate
- centralized runtime features

### 11.4 State Design Rule

`session.state` must store only small, serializable data such as:

- current job id
- stage name
- chunk manifest metadata
- validation summaries
- paths or artifact keys

It must not store the full transcript body for later instruction templating.

### 11.5 Artifact Design Rule

Large stage outputs must live in artifacts or working files.

Recommended working structure:

```text
jptranscript_app/
├── Output/
├── Work/
│   └── <job_id>/
│       ├── manifest.json
│       ├── stage0_raw.txt
│       ├── stage1_chunks/
│       ├── stage1_merged.txt
│       ├── stage2_chunks/
│       ├── stage2_merged.md
│       ├── stage3_furigana.txt
│       ├── stage4_refined.txt
│       ├── stage5_chunks/
│       ├── stage5_merged.md
│       ├── stage6_output.html
│       └── stage7_output.html
```

This directory is essential for resumability, debugging, and chunk-level retries.

---

## 12. End-to-End Workflow

The seven product stages remain, but their implementation pattern changes.

### 12.1 Stage 0: Input Ingestion and Job Setup

Responsibilities:

- accept pasted text or a file path
- validate the input source
- normalize line endings
- create a job id
- write the raw source text to a working artifact
- initialize a manifest

No LLM is needed for this stage.

Example manifest skeleton:

```json
{
  "job_id": "20260414-001",
  "source_type": "file",
  "source_path": "sample.txt",
  "stages": {
    "optimization": {"status": "pending"},
    "paragraph": {"status": "pending"},
    "furigana": {"status": "pending"},
    "refinement": {"status": "pending"},
    "glossary": {"status": "pending"},
    "html": {"status": "pending"},
    "beautify": {"status": "pending"}
  }
}
```

### 12.2 Stage 1: Optimization

Pattern:

- token-aware chunking
- per-chunk LLM map step
- deterministic merge
- deterministic validation
- chunk-local repair if needed

Output:

- cleaned transcript text

### 12.3 Stage 2: Paragraph Structuring

Pattern:

- chunk on topic-preserving boundaries
- per-chunk LLM structuring pass
- global reduce pass to reconcile headings and table of contents
- deterministic validation

Output:

- Markdown document with sections and TOC

### 12.4 Stage 3: Furigana Annotation

Pattern:

- deterministic `fugashi` annotation over the full text or bounded chunks
- optional targeted LLM review only for ambiguous readings
- deterministic validation

Output:

- fully annotated text

### 12.5 Stage 4: Furigana Refinement

Pattern:

- pure Python only

Output:

- refined furigana text

### 12.6 Stage 5: Glossary Annotation

Pattern:

- section-aware chunking using Stage 2 structure
- per-chunk LLM glossary annotation
- global reducer to normalize marker numbering and deduplicate glossary intent
- deterministic validation and repair

Output:

- Markdown with inline markers and glossary appendix

### 12.7 Stage 6: HTML Generation

Pattern:

- pure Python conversion
- HTML escaping and sanitization
- semantic validation

Output:

- complete HTML5 document

### 12.8 Stage 7: Beautification and Save

Pattern:

- pure Python template injection
- final file save
- no LLM

Output:

- saved final HTML file in `Output/`

---

## 13. Long-Content Processing Strategy

This section is the core product requirement for robustness.

### 13.1 Why Long Content Currently Fails

Long inputs currently fail for two reasons:

1. the app sends too much text to the model before chunking can help
2. the workflow repeatedly re-sends large intermediate documents through LLM-only agents

The new design must solve both.

### 13.2 Required Processing Pattern: Map -> Reduce -> Repair

For all LLM-dependent long-text stages, use this structure:

1. **Map**
   Process bounded chunks independently.
2. **Reduce**
   Merge chunk outputs into one stage artifact with deterministic logic or a small reducer pass.
3. **Repair**
   Re-run only failed chunks or only the small global consistency pass if validation fails.

### 13.3 Required Chunking Rules

Chunking must be:

- token-budget aware, not character-only
- sentence-safe
- speaker-aware where possible
- stage-specific

Required split preferences:

1. explicit section headings
2. speaker turns
3. paragraph boundaries
4. sentence boundaries
5. emergency fallback boundaries

The chunker must avoid splitting:

- inside furigana annotations
- inside glossary markers
- inside Markdown headings
- mid-sentence unless no safe option exists

### 13.4 Required Overlap Behavior

Overlap must be real, not just documented.

Each chunk may carry a short overlap window for coherence, but that overlap must be:

- marked as context-only
- excluded from final merged output
- excluded from duplicate marker numbering

### 13.5 Chunk Manifest Requirement

Each chunked stage must produce a manifest entry such as:

```json
{
  "stage": "paragraph",
  "chunk_id": "paragraph-003",
  "source_start": 4120,
  "source_end": 5988,
  "overlap_prefix_chars": 180,
  "status": "completed",
  "retries": 1,
  "output_file": "Work/20260414-001/stage2_chunks/paragraph-003.md",
  "validation": {
    "pass": true,
    "heading_count": 2
  }
}
```

This is required for repair and resumability.

### 13.6 Stage-Specific Chunking Requirements

#### Optimization

- chunk primarily by speaker blocks
- reducer mostly concatenates cleaned output

#### Paragraph Structuring

- chunk by coherent narrative or speaker segments
- reducer reconciles headings and builds a global TOC

#### Furigana

- deterministic processing can operate on the whole text if memory allows
- if chunked, chunks must preserve token boundaries and existing Markdown

#### Glossary

- chunk by existing sections from Stage 2
- reducer renumbers markers globally and merges glossary entries in first-appearance order

### 13.7 Concrete Example: 12,000-Character Transcript

Example flow:

1. raw transcript is written to `stage0_raw.txt`
2. optimization splits into 8 chunks
3. chunk 5 fails validation due to low character ratio
4. only chunk 5 is retried with a smaller prompt budget
5. merged Stage 1 output becomes `stage1_merged.txt`
6. paragraph stage re-chunks the cleaned text into 6 structure-aware chunks
7. reducer rebuilds a single TOC from all headings
8. furigana runs deterministically
9. glossary stage creates 5 section-based chunks and merges numbering into one appendix
10. HTML stage renders one safe document
11. beautifier saves the final HTML

The user sees one job, not 11 manual sub-steps.

---

## 14. Stage-by-Stage Product Requirements

## 14.1 Optimization Requirements

The optimization stage must:

- remove timestamps and non-content tags
- clean obvious transcript noise
- preserve meaning
- preserve speaker attribution
- avoid summarization

Validator must check:

- non-empty output
- safe length ratio
- speaker preservation
- no marker leakage like `[Processing chunk X of Y]`

### Example

Input:

```text
[00:02:10] 鈴木さん: あのー、まあ、昨日の会議ですけどね、えーっと、配布したその資料が、なんか少し間違ってたんですよね。
```

Expected output:

```text
鈴木さん: 昨日の会議ですが、配布した資料がなんか少し間違っていました。
```

## 14.2 Paragraph Requirements

The paragraph stage must:

- preserve original wording
- insert section headings
- build a table of contents
- keep closely related sentences together

The reducer must prevent:

- duplicate TOC blocks
- contradictory heading names between chunks
- missing sections caused by naive concatenation

## 14.3 Furigana Requirements

The furigana stage must:

- use deterministic morphological analysis first
- preserve original base text
- avoid double annotation
- support context-sensitive review where needed

LLM review must not be mandatory for every token. It should only be used for:

- ambiguous homographs
- low-confidence reading cases
- proper nouns that are suspicious in context

## 14.4 Furigana Refinement Requirements

This stage must be pure Python.

It must:

- correctly target only annotation spans
- remove furigana for configured common words
- preserve furigana on the first three appearances of other annotated items
- never alter surrounding sentence text

## 14.5 Glossary Requirements

This stage must:

- annotate difficult items conservatively
- maintain sequential numbering
- keep body text unchanged except for marker insertion
- ensure every marker has one entry
- ensure every entry has required fields

The reducer must be responsible for:

- global numbering
- duplicate resolution
- final glossary assembly

## 14.6 HTML Requirements

The converter must:

- escape unsafe input
- produce valid HTML5
- generate working ruby
- generate working glossary links and backlinks
- render a valid TOC structure

The converter must not:

- allow raw `<script>` tags from the transcript to execute
- emit broken nesting
- silently drop glossary content

## 14.7 Beautification Requirements

Beautification must:

- preserve document structure
- keep output self-contained when possible
- remain readable for Japanese text
- support print output

If full offline portability is required, avoid runtime dependency on Google Fonts.

---

## 15. Orchestration Requirements

### 15.1 Required Orchestration Pattern

The next implementation must use a **custom ADK agent** or equivalent explicit control flow for the main workflow.

The orchestrator must:

- read and write job manifests
- call stage processors in order
- checkpoint after each stage
- retry failed chunks
- stop cleanly with actionable errors

### 15.2 Why Standard LlmAgent Chaining Is Not Enough

Predefined workflow agents are useful for ordering, but they do not solve this product’s central problem:

- long content needs artifact-aware routing
- deterministic stages must bypass the model
- retry needs chunk-local control
- state must store references, not giant text bodies

The orchestrator needs direct access to `ctx.session.state` and artifact paths.

### 15.3 State Key Conventions

Recommended state shape:

```text
job_id
current_stage
temp:active_chunk_id
temp:last_validation_report
final_output_path
```

Avoid:

```text
step1_output = <entire cleaned transcript>
step2_output = <entire structured markdown>
```

Those large values belong in artifacts, not templated state.

---

## 16. LLM Invocation Requirements

### 16.1 Required Call Discipline

Every LLM invocation for long content must be explicit and bounded.

Required inputs:

- stage-specific prompt
- chunk payload
- optional small context summary
- structured output expectation when useful

Forbidden pattern:

- full prior document pasted into the instruction field via state templating

### 16.2 Required LLM Wrapper Features

The LLM wrapper around Ollama or LiteLLM must support:

- configurable model name
- retries with backoff
- timeout handling
- structured output mode where possible
- per-call metadata logging
- `keep_alive` for chunk batches

### 16.3 Required Runtime Benchmarking

Context length must be benchmarked locally at:

- `8192`
- `16384`
- `32768`
- `64000`

Choose the largest setting that remains stable and does not push substantial model execution onto CPU when observed through `ollama ps`.

The product must not assume that the theoretical maximum context is the practical best setting.

---

## 17. Security and Safety Requirements

### 17.1 File Safety

`read_transcript_file()` must:

- resolve paths safely
- reject traversal outside the allowed app directory
- raise structured errors, not return fake content strings

### 17.2 HTML Safety

All user-provided or transcript-derived text must be HTML-escaped before insertion except for explicitly generated safe markup.

This includes:

- headings
- paragraph text
- glossary content
- title text

### 17.3 Browser Safety

The final output must not execute arbitrary transcript content as HTML or JavaScript.

### 17.4 Data Safety

If future LiteLLM versions are upgraded, dependency hygiene must follow current ADK security advisories before shipping.

---

## 18. Error Handling and Recovery Requirements

The system must classify failures by scope.

### 18.1 Chunk-Local Failures

Examples:

- model timeout
- malformed chunk output
- chunk validator failure

Recovery:

- retry same chunk
- reduce chunk size
- tighten structured response format
- record retry count in manifest

### 18.2 Stage-Level Failures

Examples:

- reducer cannot reconcile headings
- glossary numbering cannot be normalized
- HTML validation fails

Recovery:

- run repair pass
- rebuild only the failing stage from stage artifacts

### 18.3 Job-Level Failures

Examples:

- model unavailable
- Python environment incompatible
- output directory not writable

Recovery:

- stop cleanly
- preserve all intermediate artifacts
- report actionable recovery instructions

### 18.4 Required Failure Messages

User-visible errors must be concrete.

Good:

```text
Stage 5 failed on glossary chunk 3 after 2 retries because marker numbering could not be normalized. Intermediate files were preserved in Work/20260414-001/.
```

Bad:

```text
Error occurred.
```

---

## 19. Testing Requirements

The current test suite is insufficient. The next implementation must add comprehensive tests.

### 19.1 Unit Tests

Required coverage:

- chunk boundary selection
- overlap exclusion during merge
- furigana annotation correctness
- furigana refinement span targeting
- glossary validation strictness
- HTML escaping
- TOC structure validity
- path traversal rejection

### 19.2 Integration Tests

Required coverage:

- pasted text workflow
- file input workflow
- resumable chunk retry
- stage checkpointing
- final output file creation

### 19.3 Long-Form Regression Tests

Required fixtures:

- short input under 500 characters
- medium input around 2,000 characters
- long input around 8,000 to 15,000 Japanese characters
- input with many speaker turns
- input with no headings
- input with pre-existing furigana
- malicious HTML-like transcript content

### 19.4 Browser Output Validation

At minimum, tests should verify:

- valid HTML structure
- no raw script injection
- glossary anchors exist
- backlinks exist
- nav closes correctly

---

## 20. Acceptance Criteria

The revised product may be accepted only when all of the following are true:

1. Long transcripts are chunked before any large LLM payload is formed.
2. No deterministic stage requires an `LlmAgent`.
3. Large stage artifacts are stored outside `session.state`.
4. `refine_furigana()` is corrected and covered by regression tests.
5. HTML output escapes unsafe content.
6. Glossary validation rejects missing required fields.
7. File traversal is blocked.
8. Integration tests exercise the real orchestration path.
9. Python runtime is upgraded to a supported version.
10. The final HTML is written to `jptranscript_app/Output/` unless product requirements explicitly change.

---

## 21. Delivery Roadmap

## Phase 0: Platform Stabilization

Goal:

- upgrade runtime baseline
- remove broken assumptions

Tasks:

- move project to Python `3.10+`
- align docs on output path
- replace broken scratch runner
- add `Work/` artifact structure

## Phase 1: Safety and Correctness Repairs

Goal:

- fix known correctness bugs before larger refactors

Tasks:

- fix `refine_furigana()`
- fix HTML escaping
- fix TOC closing behavior
- harden glossary validator
- harden file path handling
- remove chunk marker leakage

## Phase 2: Orchestration Rewrite

Goal:

- replace full-text `LlmAgent` chaining with artifact-aware control flow

Tasks:

- create ADK `App`
- implement custom orchestrator
- move large outputs to artifact files
- store only references in session state

## Phase 3: Long-Content Pipeline

Goal:

- make long transcript processing robust

Tasks:

- implement token-aware chunking
- implement map/reduce/repair for Stages 1, 2, and 5
- add chunk manifests and retries

## Phase 4: Performance and Quality Tuning

Goal:

- optimize for the local machine

Tasks:

- benchmark context sizes
- benchmark chunk sizes
- tune prompts for chunk workers only
- reduce unnecessary model passes

## Phase 5: Final Product Hardening

Goal:

- make the app dependable as a local study tool

Tasks:

- add comprehensive regression coverage
- add resumability
- improve job status reporting
- document supported workflows clearly

---

## 22. Open Questions

These questions do not block the product direction, but should be resolved during implementation.

1. Should the final HTML remain fully offline, including fonts?
2. Should Stage 3 furigana review use a second, smaller local model for ambiguity checks?
3. Should the glossary reducer deduplicate semantically similar entries across sections or preserve first occurrence only?
4. Should the reducer for Stage 2 use deterministic heading synthesis rules before any LLM summary pass?
5. Should long-job metadata also be exposed in the ADK UI as structured status events?

Until answered, implementation should choose the simplest option that preserves robustness.

---

## 23. References

Official references reviewed while preparing this PRD:

- Google ADK state documentation
- Google ADK workflow agent documentation
- Google ADK custom agent documentation
- Google ADK App documentation
- Google ADK LiteLLM connector documentation
- Ollama context length documentation
- Ollama chat API documentation
- Google DeepMind Gemma 4 product page
- Ollama Gemma 4 library page

These references inform the architectural direction but do not override local product requirements.

---

## 24. Final Directive

Future development of `jptranscript_app` must optimize for **robust long-document local processing**, not for preserving the current prototype structure.

The central implementation rule is:

> **Chunk early, store artifacts, keep state small, and use the LLM only where genuine reasoning is required.**

That rule should guide every future code change.
