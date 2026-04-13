# JPTranscriptADK Project Architecture

## Purpose
Convert raw Japanese podcast/YouTube transcripts into learner-friendly HTML documents using a local AI agent pipeline.

## Stack
- **Framework**: Google ADK (Agent Development Kit)
- **LLM**: Gemma 4 26B via Ollama (`ollama_chat/gemma4-agent`, num_ctx=8192, temp=0.2)
- **Hardware**: Apple M2 Max, 32GB RAM
- **Dependencies**: google-adk, litellm, fugashi, unidic-lite
- **Interface**: `adk web` (http://localhost:8000)

## Architecture
- **Pattern**: SequentialAgent + LoopAgent for quality validation
- **7-step pipeline**: Optimization → Paragraph → Furigana → Refinement → Glossary → HTML → Beautify
- **Three tiers**:
  - Tier 1 (LLM-Primary): Steps 1, 2, 5 — wrapped in LoopAgent
  - Tier 2 (Hybrid): Step 3 — MeCab + LLM review, wrapped in LoopAgent
  - Tier 3 (Tool-Primary): Steps 4, 6, 7 — pure Python tools, no loop

## Key Files
- `jptranscript_app/agent.py` — Root SequentialAgent
- `jptranscript_app/agents/` — Sub-agent definitions
- `jptranscript_app/tools/` — Python tool functions
- `jptranscript_app/prompts/` — Condensed system prompts for Gemma 4
- `jptranscript_app/templates/default_style.css` — Pre-built CSS
- `jptranscript_app/Output/` — Generated HTML files
- `jptranscript_app/implementation.md` — Full implementation plan

## Existing Reference
- `hello_world/` — Working ADK agent example
- `jptranscript_app/.agents/skills/` — Original SKILL.md files (preserved for reference)
- `README.md` — Tutorial for ADK + Ollama setup
