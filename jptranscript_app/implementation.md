# JP Transcript ADK — Implementation Plan

> **Status**: Approved  
> **Target Platform**: macOS · Apple M2 Max · 32 GB RAM  
> **LLM**: Customized `gemma4:26b` via Ollama  
> **Framework**: Google ADK (Agent Development Kit)  
> **Interface**: `adk web` (http://localhost:8000)

---

## Table of Contents

- [1. Overview](#1-overview)
- [2. Resolved Design Decisions](#2-resolved-design-decisions)
- [3. Architecture](#3-architecture)
- [4. Skill-to-Agent Mapping](#4-skill-to-agent-mapping)
- [5. Long Text Handling Strategy](#5-long-text-handling-strategy)
- [6. Quality Assurance — LoopAgent Validators](#6-quality-assurance--loopagent-validators)
- [7. Error Handling](#7-error-handling)
- [8. Project File Structure](#8-project-file-structure)
- [9. Implementation Phases](#9-implementation-phases)
- [10. Verification Plan](#10-verification-plan)

---

## 1. Overview

This document describes the complete plan for transforming the existing `jptranscript_app` workflow — a 7-step sequential pipeline that converts raw Japanese podcast/YouTube transcripts into polished, learner-friendly HTML — from a cloud-LLM-driven system into a **fully local AI agent** application.

### Current System

- Pipeline orchestrated by cloud LLMs (OpenAI/Claude) via Codex
- Each step guided by a SKILL.md prompt document under `.agents/skills/`
- 7 mandatory sequential steps: Optimization → Paragraph → Furigana → Furigana Refinement → Glossary → HTML → Beautification
- Input: raw Japanese transcript text or `.txt` file
- Output: single self-contained HTML file

### Target System

- **Google ADK** as the agent framework
- **Ollama** as the local model server
- **Gemma 4 26B** (customized) as the LLM brain running on Apple M2 Max (32 GB)
- **ADK Web** (`adk web`) as the user-facing chat interface
- **`fugashi` + `unidic-lite`** for reliable Japanese morphological analysis
- Same 7-step pipeline, but with deterministic Python tools handling mechanical steps

---

## 2. Resolved Design Decisions

| Decision | Resolution |
|:---|:---|
| **LLM model** | Customized `gemma4:26b` via Ollama (`gemma4-agent` profile with `num_ctx=8192`, `temperature=0.2`) |
| **Hardware** | Apple M2 Max, 32 GB RAM |
| **Agent pattern** | `SequentialAgent` (base) + `LoopAgent` (quality validation on LLM-dependent steps) |
| **Furigana tooling** | `fugashi` + `unidic-lite` (MeCab-based), installed in project `.venv` |
| **Input method** | Both: pasted text via ADK Web chat **and** file reading from a local directory |
| **Output directory** | Existing `jptranscript_app/Output/` |
| **Beautification** | Pre-built CSS template (not LLM-generated CSS) |
| **Virtual environment** | Project-root `.venv` |

---

## 3. Architecture

### Design Pattern: SequentialAgent + LoopAgent

The pipeline maps to ADK's `SequentialAgent`. To ensure output quality, **LLM-dependent steps** (Tiers 1 and 2) are wrapped in a `LoopAgent` that pairs the processing agent with a validator agent. The validator checks objective quality metrics and calls `exit_loop` when satisfied or provides feedback for the next iteration.

**Deterministic steps** (Tier 3) do not need loops — Python tools produce correct results on the first pass.

### Three-Tier Classification

| Tier | Steps | LLM Role | Python Tool Role | Loop |
|:---|:---|:---|:---|:---|
| **Tier 1 — LLM-Primary** | 1 (Optimization), 2 (Paragraph), 5 (Glossary) | Primary text processor | Chunking, validation, I/O | LoopAgent (max 3) |
| **Tier 2 — Hybrid** | 3 (Furigana) | Reviews automated output | Primary processor (MeCab) | LoopAgent (max 2) |
| **Tier 3 — Tool-Primary** | 4 (Refinement), 6 (HTML), 7 (Beautify) | Calls tool, passes through | Full processor | None |

### Pipeline Diagram

```
SequentialAgent("jptranscript_pipeline")
│
├── LoopAgent("step1_optimization_loop", max_iterations=3)
│   ├── optimization_agent          ← LlmAgent (Tier 1)
│   └── optimization_validator      ← LlmAgent + validate_optimization tool + exit_loop
│
├── LoopAgent("step2_paragraph_loop", max_iterations=3)
│   ├── paragraph_agent             ← LlmAgent (Tier 1)
│   └── paragraph_validator         ← LlmAgent + validate_paragraph tool + exit_loop
│
├── LoopAgent("step3_furigana_loop", max_iterations=2)
│   ├── furigana_agent              ← LlmAgent (Tier 2) + auto_add_furigana tool
│   └── furigana_validator          ← LlmAgent + validate_furigana tool + exit_loop
│
├── refinement_agent                ← LlmAgent (Tier 3) + refine_furigana tool
│
├── LoopAgent("step5_glossary_loop", max_iterations=3)
│   ├── glossary_agent              ← LlmAgent (Tier 1)
│   └── glossary_validator          ← LlmAgent + validate_glossary tool + exit_loop
│
├── html_agent                      ← LlmAgent (Tier 3) + convert_to_html tool
│
└── beautify_agent                  ← LlmAgent (Tier 3) + apply_design_template + save_html_file
```

### Data Flow Between Agents

State is shared via `output_key` on each agent and read via `{state_variable}` in subsequent agent instructions.

```
User input (raw transcript)
    │
    ▼
{user_input} ──→ optimization_agent ──→ {step1_output}
                                            │
                                            ▼
                  paragraph_agent    ──→ {step2_output}
                                            │
                                            ▼
                  furigana_agent      ──→ {step3_output}
                                            │
                                            ▼
                  refinement_agent   ──→ {step4_output}
                                            │
                                            ▼
                  glossary_agent     ──→ {step5_output}
                                            │
                                            ▼
                  html_agent         ──→ {step6_output}
                                            │
                                            ▼
                  beautify_agent     ──→ {final_html}
                                            │
                                            ▼
                                     Output/*.html file
```

---

## 4. Skill-to-Agent Mapping

### Step 1 — Optimization Agent (Tier 1)

| Attribute | Value |
|:---|:---|
| **Current skill** | `$jptranscript-optimization` |
| **ADK agent** | `optimization_agent` (LlmAgent) |
| **Instruction** | Condensed optimization rules (~400 tokens): remove timestamps, fix spacing, remove semantically empty fillers, minimal corrections |
| **Tools** | `process_optimization_chunks` — chunks long input, calls Ollama per chunk, reassembles |
| **Output key** | `step1_output` |
| **Wrapped in** | `LoopAgent("step1_optimization_loop", max_iterations=3)` |
| **Validator** | `optimization_validator` — calls `validate_optimization` tool (checks character ratio, speaker labels), calls `exit_loop` if OK |

### Step 2 — Paragraph Agent (Tier 1)

| Attribute | Value |
|:---|:---|
| **Current skill** | `$jptranscript-paragraph` |
| **ADK agent** | `paragraph_agent` (LlmAgent) |
| **Instruction** | Condensed paragraph rules (~400 tokens): insert breaks at topic shifts, add H2 subtitles, format dialogue with bold names, add table of contents |
| **Tools** | `process_paragraph_chunks` — chunks `{step1_output}`, processes, reassembles |
| **Output key** | `step2_output` |
| **Wrapped in** | `LoopAgent("step2_paragraph_loop", max_iterations=3)` |
| **Validator** | `paragraph_validator` — calls `validate_paragraph` (checks headings present, content preserved), calls `exit_loop` if OK |

### Step 3 — Furigana Agent (Tier 2 — Hybrid)

| Attribute | Value |
|:---|:---|
| **Current skill** | `$jptranscript-furigana` |
| **ADK agent** | `furigana_agent` (LlmAgent) |
| **Instruction** | "Use the auto_add_furigana tool to add furigana readings to all kanji in the input. Review the result for obvious reading errors in context. Return the furigana-annotated text." |
| **Tools** | `auto_add_furigana` — Python tool using `fugashi` + `unidic-lite` for morphological analysis, inserts `漢字（かんじ）` format |
| **Output key** | `step3_output` |
| **Wrapped in** | `LoopAgent("step3_furigana_loop", max_iterations=2)` |
| **Validator** | `furigana_validator` — calls `validate_furigana` (checks coverage: % of kanji with readings), calls `exit_loop` if coverage > 90% |

### Step 4 — Furigana Refinement Agent (Tier 3 — Tool-Primary)

| Attribute | Value |
|:---|:---|
| **Current skill** | `$jptranscript-furigana-refinement` |
| **ADK agent** | `refinement_agent` (LlmAgent) |
| **Instruction** | "Use the refine_furigana tool on the text from the previous step. Pass through the result without changes." |
| **Tools** | `refine_furigana` — Pure Python: (1) remove furigana from common-word list, (2) keep furigana only on first 3 appearances of other words |
| **Output key** | `step4_output` |
| **No LoopAgent** | Deterministic — always correct on first pass |

### Step 5 — Glossary Agent (Tier 1)

| Attribute | Value |
|:---|:---|
| **Current skill** | `$jptranscript-phase-glossary` |
| **ADK agent** | `glossary_agent` (LlmAgent) |
| **Instruction** | Condensed glossary rules (~500 tokens): identify difficult words/phrases/patterns, insert `*N` markers, generate glossary appendix with 意味, 例文, 比較 |
| **Tools** | `process_glossary_chunks` — chunks text, calls Ollama per chunk, merges annotations with sequential numbering |
| **Output key** | `step5_output` |
| **Wrapped in** | `LoopAgent("step5_glossary_loop", max_iterations=3)` |
| **Validator** | `glossary_validator` — calls `validate_glossary` (checks marker↔entry alignment, sequential numbering), calls `exit_loop` if OK |

### Step 6 — HTML Generator Agent (Tier 3 — Tool-Primary)

| Attribute | Value |
|:---|:---|
| **Current skill** | `$jptranscript-html` |
| **ADK agent** | `html_agent` (LlmAgent) |
| **Instruction** | "Use the convert_to_html tool to convert the text from the previous step into a complete HTML5 document. Pass through the result." |
| **Tools** | `convert_to_html` — Pure Python: Markdown → HTML, `漢字（かんじ）` → `<ruby>`, `*N` → `<a href="#glossary-N">`, glossary → `<section>` with backlinks |
| **Output key** | `step6_output` |
| **No LoopAgent** | Deterministic |

### Step 7 — Beautification Agent (Tier 3 — Tool-Primary)

| Attribute | Value |
|:---|:---|
| **Current skill** | `$frontend-design` |
| **ADK agent** | `beautify_agent` (LlmAgent) |
| **Instruction** | "Use the apply_design_template tool to add professional styling to the HTML. Then use save_html_file to write the final file. Report the file path to the user." |
| **Tools** | `apply_design_template` (injects CSS from `templates/default_style.css`), `save_html_file` (writes to `Output/`) |
| **Output key** | `final_html` |
| **No LoopAgent** | Deterministic |

---

## 5. Long Text Handling Strategy

### Problem

Gemma 4 with `num_ctx=8192` has a ~8192 token context window. A typical Japanese podcast transcript ranges from 3000 to 10000+ characters (~4000–15000 tokens). System prompts consume another ~500–1000 tokens.

### Solution: Adaptive Chunk Processing

For Tier 1 steps (Steps 1, 2, 5), a Python tool function handles chunking:

```
Full Transcript (~5000 chars)
        │
        ▼
 ┌─────────────────┐
 │  Chunk Splitter  │  Target: ~1500 chars/chunk
 │  (boundary-aware)│  Split at: speaker turns, paragraphs, headings
 └────┬────┬────┬───┘
      │    │    │
      ▼    ▼    ▼
   Chunk  Chunk  Chunk
    1      2      3
      │    │    │
      ▼    ▼    ▼
  ┌──────────────┐
  │ Ollama API   │  Each chunk: system prompt + chunk → processed chunk
  │ (per chunk)  │  Via litellm.completion() direct call
  └──────────────┘
      │    │    │
      ▼    ▼    ▼
   Result Result Result
    1      2      3
      │    │    │
      ▼    ▼    ▼
 ┌─────────────────┐
 │   Reassembler   │
 └─────────────────┘
        │
        ▼
  Processed Text (full)
```

### Chunking Rules

| Rule | Details |
|:---|:---|
| **Target chunk size** | ~1500 Japanese characters (~2000–3000 tokens) |
| **Split boundaries** | Speaker turns (`Name：`), double newlines, Markdown headings (`## `) |
| **Never split** | Mid-sentence (no splitting at `、`, only at `。` or newlines) |
| **Overlap context** | ~200 characters from previous chunk appended (marked, not processed) for coherence |
| **Context budget** | System prompt (~500 tok) + input (~2500 tok) + output (~4000 tok) ≈ 7000 tokens |
| **Fallback** | If no natural boundary found, split at nearest `。` within target range |

### Step-Specific Chunking Notes

| Step | Chunking Consideration |
|:---|:---|
| Step 1 (Optimization) | Chunk by speaker turns. Each chunk is independent. |
| Step 2 (Paragraph) | Chunk by speaker blocks. Cross-chunk topic detection: the tool includes the last heading from the previous chunk as context. |
| Step 3 (Furigana) | No chunking needed — `fugashi` processes full text in memory. LLM review can be chunked if needed. |
| Step 4 (Refinement) | No chunking needed — pure Python, processes full text. |
| Step 5 (Glossary) | Chunk by sections (after Step 2 created headings). Global marker numbering maintained by the tool across chunks. |
| Step 6 (HTML) | No chunking needed — pure Python conversion. |
| Step 7 (Beautify) | No chunking needed — template injection. |

---

## 6. Quality Assurance — LoopAgent Validators

Each Tier 1 step is wrapped in a `LoopAgent` containing:
1. The **processor agent** (does the work)
2. A **validator agent** (checks quality, calls `exit_loop` or provides feedback)

### Validator Agent Pattern

```python
from google.adk.agents import LlmAgent
from google.adk.tools import exit_loop

validator_agent = LlmAgent(
    model=local_model,
    name="step_N_validator",
    instruction="""
    Use the validate_step_N tool to check the quality of the current output.
    The tool returns a validation report with pass/fail metrics.
    
    If all checks pass: call exit_loop to proceed to the next step.
    If any check fails: explain what went wrong and what needs to be fixed
    so the processor agent can try again.
    """,
    tools=[validate_step_N, exit_loop],
)
```

### Validation Checks Per Step

#### Step 1 — Optimization Validation

| Check | Method | Threshold |
|:---|:---|:---|
| Content completeness | `len(output) / len(input)` character ratio | Must be > 0.70 |
| Speaker label preservation | Regex count of `Name：` patterns | Must match input count |
| No added content | Output character count | Must be ≤ input character count |
| No empty output | `len(output.strip())` | Must be > 0 |

#### Step 2 — Paragraph Validation

| Check | Method | Threshold |
|:---|:---|:---|
| Headings present | Count `## ` patterns | Must be ≥ 1 |
| Content preserved | Character count ratio (excluding Markdown markup) | Must be > 0.95 |
| Table of contents | Check for `**目次**` pattern | Must be present |
| Bold speaker names | Count `**Name**：` patterns | Must match input speaker count |

#### Step 3 — Furigana Validation

| Check | Method | Threshold |
|:---|:---|:---|
| Furigana coverage | Count kanji words with `（reading）` / total kanji words | Must be > 0.90 |
| Format correctness | All readings use full-width parentheses `（）` | 100% |
| Content preserved | Base text (without furigana) matches input | Character diff < 1% |

#### Step 5 — Glossary Validation

| Check | Method | Threshold |
|:---|:---|:---|
| Marker-entry alignment | Count `*N` markers = count glossary entries | Must match |
| Sequential numbering | Markers are `*1, *2, *3, ...` in order | Must be sequential |
| Glossary structure | Each entry has `意味`, `例文`, `比較` | 100% |
| Separator present | `---` exists between body and glossary | Must be present |
| Content preserved | Body text (without markers) ≈ input text | Character diff < 2% |

---

## 7. Error Handling

| Failure Mode | Detection | Recovery |
|:---|:---|:---|
| **Ollama not running** | Connection error on first API call | Agent returns message: "Ollama is not running. Please start with `ollama serve`." |
| **Model not found** | `ollama list` check in startup tool | Agent returns message: "Model gemma4-agent not found. Run the Modelfile creation steps from README.md." |
| **Context overflow** | Chunk produces truncated or empty output | Reduce chunk size by 30% and retry (up to 2 retries) |
| **Garbled output** | Validation fails: character ratio far outside threshold | Retry within LoopAgent (up to max_iterations). If still fails, pass through original text with a warning. |
| **Missing furigana** | Post-Step-3 validation: coverage < 90% | LoopAgent retries. Fallback: MeCab output is already reliable; skip LLM review. |
| **LLM won't call tool** | No tool call detected in agent response | Instruction reinforcement (strong wording: "You MUST call the tool"). |
| **Glossary numbering mismatch** | Validator detects misaligned markers/entries | LoopAgent retries with explicit feedback about the mismatch. |
| **HTML malformation** | Python HTML converter validates its own output | Use Python fallback converter — deterministic, always produces valid HTML. |
| **File write failure** | `save_html_file` returns error | Agent reports the error. User checks Output/ directory permissions. |

---

## 8. Project File Structure

```
ADKApplications/                         ← Project root
├── .env                                 ← OLLAMA_API_BASE="http://localhost:11434"
├── .venv/                               ← Python virtual environment
├── README.md                            ← Tutorial documentation
│
├── hello_world/                         ← Existing reference agent
│   ├── __init__.py
│   └── agent.py
│
└── jptranscript_app/                    ← [NEW] ADK agent package
    ├── __init__.py                      ← from . import agent
    ├── agent.py                         ← Root SequentialAgent + model config
    ├── .env                             ← Agent-specific env vars
    ├── implementation.md                ← This document
    │
    ├── agents/                          ← Sub-agent definitions
    │   ├── __init__.py
    │   ├── optimization.py              ← Step 1 (Tier 1) processor + validator
    │   ├── paragraph.py                 ← Step 2 (Tier 1) processor + validator
    │   ├── furigana.py                  ← Step 3 (Tier 2) processor + validator
    │   ├── furigana_refinement.py       ← Step 4 (Tier 3) — tool only
    │   ├── glossary.py                  ← Step 5 (Tier 1) processor + validator
    │   ├── html_generator.py            ← Step 6 (Tier 3) — tool only
    │   └── beautifier.py               ← Step 7 (Tier 3) — tool only
    │
    ├── tools/                           ← Python tool functions
    │   ├── __init__.py
    │   ├── text_processing.py           ← Chunking, validation, file I/O
    │   ├── furigana_tools.py            ← MeCab-based furigana + refinement
    │   ├── html_converter.py            ← Markdown → HTML + ruby + glossary
    │   └── beautifier_tools.py          ← CSS template injection
    │
    ├── prompts/                         ← Condensed system prompts for Gemma 4
    │   ├── optimization.md              ← ~400 tokens (from ~1200 token SKILL.md)
    │   ├── paragraph.md                 ← ~400 tokens
    │   ├── furigana_review.md           ← ~200 tokens (review-only prompt)
    │   ├── glossary.md                  ← ~500 tokens
    │   └── tool_caller.md               ← ~100 tokens (generic "call the tool" prompt)
    │
    ├── templates/                       ← Static assets
    │   └── default_style.css            ← Pre-built CSS for HTML output
    │
    ├── tests/                           ← Test suite
    │   ├── __init__.py
    │   ├── test_text_processing.py
    │   ├── test_furigana_tools.py
    │   ├── test_html_converter.py
    │   └── test_integration.py
    │
    ├── Output/                          ← Generated HTML files (existing)
    │
    └── .agents/                         ← Existing skills (preserved for reference)
        └── skills/
            └── (existing SKILL.md files)
```

---

## 9. Implementation Phases

### Phase 1 — Foundation (Estimated: ~1 hour)

**Goal**: Set up the project structure, dependencies, and Ollama model.

#### 1.1 Create the Modelfile for gemma4-agent (if not already done)

```bash
cat << 'EOF' > Modelfile
FROM gemma4:26b
PARAMETER num_ctx 8192
PARAMETER temperature 0.2
EOF
ollama create gemma4-agent -f Modelfile
```

#### 1.2 Install Python dependencies in project `.venv`

```bash
cd /path/to/ADKApplications
source .venv/bin/activate
pip install google-adk litellm fugashi unidic-lite
```

#### 1.3 Create project scaffold

Create the following files:

- `jptranscript_app/__init__.py` — `from . import agent`
- `jptranscript_app/.env` — agent-specific env vars
- `jptranscript_app/agents/__init__.py` — empty
- `jptranscript_app/tools/__init__.py` — empty
- `jptranscript_app/prompts/` — directory
- `jptranscript_app/templates/` — directory
- `jptranscript_app/tests/__init__.py` — empty

#### 1.4 Create minimal `agent.py` skeleton

```python
import os
from google.adk.agents import SequentialAgent
from google.adk.models.lite_llm import LiteLlm
from google.auth.credentials import AnonymousCredentials
import vertexai

# Authentication bypass for local-only use
vertexai.init(
    project="local-dummy-project",
    location="us-central1",
    credentials=AnonymousCredentials()
)

# Connect to Ollama via LiteLlm
local_model = LiteLlm(model="ollama_chat/gemma4-agent")

# Placeholder — will be replaced in Phase 3
root_agent = SequentialAgent(
    name="jptranscript_pipeline",
    description=(
        "Transforms raw Japanese podcast or YouTube transcript text "
        "into a refined, learner-friendly HTML document through a "
        "7-step sequential pipeline."
    ),
    sub_agents=[]  # To be populated in Phase 3
)
```

#### 1.5 Verify ADK discovery

```bash
adk web  # Should show jptranscript_app in the dropdown
```

**Deliverables**: Working project scaffold, `adk web` recognizes the agent, dependencies installed.

---

### Phase 2 — Tool Development (Estimated: ~3 hours)

**Goal**: Implement all Python tool functions that the agents will rely on.

#### 2.1 `tools/text_processing.py`

Core utilities used across multiple steps.

**Functions to implement**:

| Function | Purpose | Used By |
|:---|:---|:---|
| `read_transcript_file(file_path: str) -> str` | Reads a .txt file from a given path relative to `jptranscript_app/` | Input handling |
| `chunk_text(text: str, max_chars: int = 1500) -> list[str]` | Splits text at natural boundaries (speaker turns, paragraphs, headings). Returns list of chunks. | Steps 1, 2, 5 |
| `reassemble_chunks(chunks: list[str]) -> str` | Joins processed chunks back into a single text | Steps 1, 2, 5 |
| `process_text_chunks(text: str, system_prompt: str, model: str = "ollama_chat/gemma4-agent") -> str` | Orchestrates: chunk → call Ollama per chunk → reassemble. Uses `litellm.completion()` directly. | Steps 1, 2, 5 |
| `validate_optimization(input_text: str, output_text: str) -> dict` | Returns validation report: character ratio, speaker count, etc. | Step 1 validator |
| `validate_paragraph(input_text: str, output_text: str) -> dict` | Returns validation report: heading count, TOC presence, etc. | Step 2 validator |
| `validate_glossary(text: str) -> dict` | Returns validation report: marker-entry alignment, numbering, etc. | Step 5 validator |
| `save_html_file(html_content: str, topic_slug: str = "") -> str` | Writes HTML to `Output/`, returns file path. Auto-generates filename from topic. Appends numeric suffix if file exists. | Step 7 |

#### 2.2 `tools/furigana_tools.py`

Japanese morphological analysis and furigana logic.

**Functions to implement**:

| Function | Purpose | Used By |
|:---|:---|:---|
| `auto_add_furigana(text: str) -> str` | Uses `fugashi` to tokenize, extracts readings, inserts `漢字（かんじ）` format. Handles compound words, okurigana, mixed kanji-kana. Skips kana-only tokens. | Step 3 |
| `validate_furigana(text: str) -> dict` | Counts kanji words with/without furigana. Returns coverage percentage. | Step 3 validator |
| `refine_furigana(text: str) -> str` | Pure Python implementation of the full refinement algorithm: (1) remove furigana from common-word list (80+ entries), (2) keep furigana on first 3 appearances of other words, (3) handle stem matching for inflected forms | Step 4 |

**Common-word list**: Implemented as a Python set/dict containing all entries from the SKILL.md:
```python
COMMON_WORDS = {
    ("日本", "にほん"), ("私", "わたし"), ("行", "い"), ("中", "なか"),
    ("方", "かた"), ("方", "ほう"), ("思", "おも"), #... (80+ entries)
}
```

#### 2.3 `tools/html_converter.py`

Markdown-to-HTML conversion with Japanese-specific features.

**Functions to implement**:

| Function | Purpose | Used By |
|:---|:---|:---|
| `convert_to_html(markdown_text: str) -> str` | Full Markdown → HTML conversion: headings, paragraphs, lists, bold, code. Plus: `漢字（かんじ）` → `<ruby>`, `*N` → `<a href>`, glossary section → `<section>` with backlinks, semantic HTML5 structure | Step 6 |

The converter uses regex patterns and a lightweight Markdown parser (not a full library) to:
1. Extract and convert Markdown headings to `<h1>`–`<h6>`
2. Convert paragraphs to `<p>`
3. Convert furigana patterns to `<ruby>漢字<rt>かんじ</rt></ruby>`
4. Convert `*N` markers to `<a href="#glossary-N" id="ref-N" class="footnote">*N</a>`
5. Convert the glossary appendix to `<section>` with `<ol>` and backlinks
6. Wrap in complete HTML5 document structure

#### 2.4 `tools/beautifier_tools.py`

CSS template handling.

**Functions to implement**:

| Function | Purpose | Used By |
|:---|:---|:---|
| `apply_design_template(html: str) -> str` | Loads `templates/default_style.css`, injects into `<style>` in html `<head>`. Adds Google Fonts link for Noto Sans JP. | Step 7 |

#### 2.5 `templates/default_style.css`

Pre-built CSS that achieves the `$frontend-design` goals:

- **Typography**: Noto Sans JP (Google Fonts), readable sizing
- **Layout**: Centered reading column, max-width 800px, generous padding
- **Reading comfort**: line-height 1.8 for Japanese, clear heading hierarchy
- **Ruby styling**: `rt` at 0.5em, positioned above kanji
- **Glossary links**: Subtle interactive styling (underline, color change on hover)
- **Navigation**: Sticky table-of-contents, smooth scroll to anchors
- **Mobile responsive**: Adapts to phone widths
- **Print optimized**: `@media print` rules for clean A4 output (no navigation, no background colors, adjusted font sizes)
- **Dark/light mode**: `prefers-color-scheme` media query

**Deliverables**: All tool modules implemented and individually testable.

---

### Phase 3 — Agent Implementation (Estimated: ~3 hours)

**Goal**: Define all 7 agent modules, condensed prompts, and wire the SequentialAgent.

#### 3.1 Create condensed prompts in `prompts/`

For each Tier 1 step, condense the original SKILL.md into a prompt optimized for Gemma 4:
- Remove explanatory prose and analogies
- Keep core rules as numbered bullet points
- Include exactly 1 input/output example
- Keep the hard guardrails as imperative sentences
- Target < 500 tokens per prompt

Example condensation for `prompts/optimization.md`:

```markdown
Clean this Japanese transcript. Apply these edits in order:

1. Remove timestamps like [00:15:30] and non-content tags.
2. Fix unnatural spacing between characters.
3. Remove fillers that add no meaning: あのー, えーっと, まあ, ええ.
   Keep fillers that carry tone or hesitation.
4. Fix obvious typos, particle errors, and broken grammar.
5. Do NOT summarize, compress, rewrite, or add content.
6. Preserve speaker labels, names, numbers, and meaning.

Example:
Input: [00:02:10] 鈴木さん: あのー、まあ、昨日の会議ですけどね、えーっと、配布したその資料が、なんか少し間違ってたんですよね。
Output: 鈴木さん: 昨日の会議ですが、配布した資料がなんか少し間違っていました。

Return only the cleaned transcript.
```

Also create `prompts/tool_caller.md`:

```markdown
You must use the provided tool to process the text.
Call the tool with the text from the previous step.
Return the tool's output without changes.
```

#### 3.2 Implement each agent module in `agents/`

Each module exports the relevant agents (processor + validator if applicable).

**Template for Tier 1 agent modules** (e.g., `agents/optimization.py`):

```python
import pathlib
from google.adk.agents import LlmAgent
from google.adk.tools import exit_loop
from ..tools.text_processing import process_text_chunks, validate_optimization

# Load condensed prompt
_prompt_path = pathlib.Path(__file__).parent.parent / "prompts" / "optimization.md"
_prompt = _prompt_path.read_text(encoding="utf-8")

def create_optimization_agents(model):
    """Create processor + validator for Step 1."""
    
    processor = LlmAgent(
        model=model,
        name="optimization_processor",
        instruction=(
            f"{_prompt}\n\n"
            "Process the transcript text. If the text is long, "
            "use the process_optimization_chunks tool."
        ),
        tools=[process_text_chunks_optimization],
        output_key="step1_output",
    )
    
    validator = LlmAgent(
        model=model,
        name="optimization_validator",
        instruction=(
            "Use the validate_optimization tool to check the quality of step1_output. "
            "If all checks pass, call exit_loop. "
            "If any check fails, explain what needs to be fixed."
        ),
        tools=[validate_optimization, exit_loop],
    )
    
    return processor, validator
```

**Template for Tier 3 agent modules** (e.g., `agents/furigana_refinement.py`):

```python
from google.adk.agents import LlmAgent
from ..tools.furigana_tools import refine_furigana

def create_refinement_agent(model):
    """Create Step 4 agent — pure tool call."""
    
    return LlmAgent(
        model=model,
        name="furigana_refinement",
        instruction=(
            "Use the refine_furigana tool on the text from step3_output: {step3_output}. "
            "Return the tool result exactly as-is."
        ),
        tools=[refine_furigana],
        output_key="step4_output",
    )
```

#### 3.3 Wire everything in `agent.py`

```python
from google.adk.agents import SequentialAgent, LoopAgent

# Import agent factories
from .agents.optimization import create_optimization_agents
from .agents.paragraph import create_paragraph_agents
from .agents.furigana import create_furigana_agents
from .agents.furigana_refinement import create_refinement_agent
from .agents.glossary import create_glossary_agents
from .agents.html_generator import create_html_agent
from .agents.beautifier import create_beautify_agent

# Create all agents
opt_proc, opt_val = create_optimization_agents(local_model)
par_proc, par_val = create_paragraph_agents(local_model)
fur_proc, fur_val = create_furigana_agents(local_model)
glo_proc, glo_val = create_glossary_agents(local_model)
ref_agent = create_refinement_agent(local_model)
htm_agent = create_html_agent(local_model)
bea_agent = create_beautify_agent(local_model)

# Assemble pipeline
root_agent = SequentialAgent(
    name="jptranscript_pipeline",
    description="Transforms raw Japanese transcripts into learner-friendly HTML",
    sub_agents=[
        LoopAgent(name="step1_optimization", sub_agents=[opt_proc, opt_val], max_iterations=3),
        LoopAgent(name="step2_paragraph", sub_agents=[par_proc, par_val], max_iterations=3),
        LoopAgent(name="step3_furigana", sub_agents=[fur_proc, fur_val], max_iterations=2),
        ref_agent,
        LoopAgent(name="step5_glossary", sub_agents=[glo_proc, glo_val], max_iterations=3),
        htm_agent,
        bea_agent,
    ]
)
```

**Deliverables**: All agents defined, prompts condensed, pipeline fully wired.

---

### Phase 4 — Integration & Testing (Estimated: ~2 hours)

**Goal**: End-to-end testing, debugging, and validation.

#### 4.1 Unit tests

Write tests for each tool module:

```bash
python -m pytest jptranscript_app/tests/ -v
```

| Test File | Key Tests |
|:---|:---|
| `test_text_processing.py` | Chunking at speaker turns, reassembly order, validation thresholds |
| `test_furigana_tools.py` | `auto_add_furigana` on known words, `refine_furigana` common-word removal and first-appearance tracking |
| `test_html_converter.py` | Ruby tag generation, glossary link/backlink pairs, complete HTML5 document structure |

#### 4.2 End-to-end test with sample transcript

Create a test script that:
1. Reads a short sample transcript (~500 chars)
2. Runs it through `adk run jptranscript_app`
3. Verifies the output HTML file exists and is valid

#### 4.3 ADK Web verification

1. Launch `adk web`
2. Select `jptranscript_app` from the dropdown
3. Paste a test transcript
4. Observe the event trace in the UI — verify all 7 steps execute
5. Open the generated HTML file in a browser

#### 4.4 Edge case testing

| Case | Expected Behavior |
|:---|:---|
| Very short input (< 100 chars) | Complete pipeline runs. No chunking needed. |
| Very long input (> 5000 chars) | Chunking activates. All chunks processed. |
| No kanji in input | Furigana step produces unchanged output. |
| No speaker labels | Paragraph step uses topic-shift detection only. |
| File input (`.txt` file path) | `read_transcript_file` tool reads and processes it. |

**Deliverables**: All tests passing, end-to-end pipeline working via ADK Web.

---

### Phase 5 — Refinement (Estimated: ~1-2 hours)

**Goal**: Optimize for Gemma 4 behavior and polish the output.

#### 5.1 Prompt tuning

Run the pipeline several times with different transcripts and adjust prompts:
- If Gemma 4 over-edits in Step 1 → strengthen "do NOT rewrite" guardrails
- If Step 2 creates too many/few sections → adjust "create new paragraph only when topic genuinely shifts"
- If Step 5 over-annotates → add "annotate 10–20 items maximum per 2000 characters"

#### 5.2 Chunk size optimization

Test with transcripts of varying lengths:
- 500 chars → no chunking
- 2000 chars → 1-2 chunks
- 5000 chars → 3-4 chunks
- 10000 chars → 7-8 chunks

Adjust `max_chars` parameter based on observed quality.

#### 5.3 CSS template polishing

Refine `templates/default_style.css` based on rendered output:
- Test with real transcript HTML in browser
- Test print layout (Ctrl+P)
- Test mobile responsiveness
- Adjust spacing, colors, and typography

#### 5.4 Performance measurement

Measure and document:
- Time per step on Apple M2 Max
- Total pipeline time for a typical transcript (~3000 chars)
- Memory usage during processing

**Deliverables**: Tuned prompts, optimized chunk size, polished CSS, performance benchmarks.

---

## 10. Verification Plan

### Automated

| Verification | Command | What It Checks |
|:---|:---|:---|
| Unit tests | `python -m pytest jptranscript_app/tests/ -v` | Tool correctness |
| Lint check | `ruff check jptranscript_app/` | Code quality |
| ADK discovery | `adk web` → check dropdown | Package structure is valid |
| Model availability | `ollama list \| grep gemma4-agent` | Ollama model is ready |

### Manual via ADK Web

1. Launch `adk web`, select `jptranscript_app`
2. Paste a known Japanese transcript
3. Monitor event trace — verify 7 steps run in sequence
4. For LoopAgent steps, verify validation pass/retry behavior
5. Check the generated HTML file: correct furigana, glossary links, CSS styling
6. Test print output from browser (File → Print → save as PDF)

### Quality Comparison

Process the same transcript through:
- The existing cloud-LLM pipeline (original workflow)
- The new local ADK pipeline

Compare:
- Content completeness (no missing text)
- Furigana accuracy (correct readings)
- Glossary quality (appropriate difficulty level, correct marker alignment)
- HTML structure (valid, semantic)
- Visual appearance (CSS styling)

Document any quality gaps for future prompt tuning.
