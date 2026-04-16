# CLAUDE.md — Autonomous Workflow for KIRA

## Project Overview
KIRA (Knowledge-driven Intelligent Reasoning Agent) is a personal AI agent framework.
It combines the best ideas from Hermes Agent and OpenClaw into a lightweight, self-improving agent.

## Directory Structure
```
kira/
  core/           — Agent loop, providers, router, models
  identity/       — SOUL.md, USER.md, RULES.md loader
  skills/         — Skill system (loader, evaluator, store)
  memory/         — Session DB (SQLite+FTS5), long-term memory
  tools/          — Tool registry + built-in tools
  channels/       — Messaging platform adapters
  scheduler/      — Cron/heartbeat system
  config/         — Settings + secrets loader
  cli/            — REPL and main entry point
  web/            — Dashboard (server.py + dashboard.html)
  integrations/   — Google OAuth, etc.
```

## How to Run
```bash
cd /Users/anjalisingh/Documents/OpenClawOrHermes
source .venv/bin/activate
kira                    # CLI REPL + dashboard at http://localhost:7777
kira serve              # Dashboard only (headless, for servers)
kira setup google       # Google OAuth setup
```

## How to Test
```bash
source .venv/bin/activate
python -m pytest tests/ -v
# Quick import check:
python -c "from kira.core.agent import Agent; print('OK')"
```

## Development Rules
- Keep total codebase under 10,000 lines
- No heavy frameworks (no LangChain, no LiteLLM, no LlamaIndex)
- Direct HTTP calls via httpx for all provider APIs
- All state is local: SQLite + markdown files
- Every tool must return a ToolResult with success, output, and optional outcome dict
- Provider adapters normalize to internal Message format (kira/core/models.py)
- Self-improving loop uses OUTCOME-BASED verification, never self-judgment
- Skills are markdown files with YAML frontmatter in skills/store/

## Key Files
- `kira/core/models.py` — All data types (Message, ToolCall, ToolSchema, etc.)
- `kira/core/agent.py` — The agent loop
- `kira/core/router.py` — Model routing + fallback
- `kira/core/providers/openai_compat.py` — Covers OpenRouter, OpenAI, Groq, Ollama, etc.
- `kira/core/providers/anthropic_adapter.py` — Anthropic Messages API
- `kira/tools/registry.py` — Tool registration and dispatch
- `kira/tools/builtin/` — Built-in tools (terminal, files, web, gmail)
- `kira/tools/builtin/gmail.py` — Gmail tools (search, read, send, draft, label)
- `kira/integrations/google_auth.py` — Google OAuth2 flow for Gmail API
- `kira/memory/sessions.py` — SQLite session database with FTS5
- `kira/identity/loader.py` — System prompt assembly from markdown files
- `kira/config/loader.py` — Config loading + defaults
- `kira/cli/main.py` — Entry point, wires everything together
- `kira/cli/repl.py` — Interactive CLI

## Adding a New Provider
1. If OpenAI-compatible: just add to settings.yaml providers section with type: openai_compatible
2. If custom API: create new adapter in kira/core/providers/ extending ProviderAdapter
3. Register in kira/cli/main.py _build_router()

## Adding a New Tool
1. Create a file in kira/tools/builtin/ (or kira/tools/custom/ for personal tools)
2. Define a class extending Tool with a schema and execute method
3. Add a register(registry) function at module level
4. It auto-discovers on startup

## Google/Gmail Setup
```bash
# 1. Get OAuth credentials from Google Cloud Console
#    (enable Gmail API, create Desktop OAuth client, download JSON)
# 2. Save as ~/.kira/google_credentials.json
# 3. Authenticate:
kira setup google
# Or from inside the REPL:
/setup google
/gmail status
```

## Phase Roadmap
- Phase 1 (DONE): Core agent, providers, tools, CLI, session DB
- Phase 1.5 (DONE): Gmail integration (search, read, send, draft, label)
- Phase 2 (DONE): Skills system with outcome-based self-improvement
- Phase 2.5 (DONE): Web dashboard (config, monitoring, activity, skills, identity editor)
- Phase 3 (NEXT): Telegram channel, scheduler/heartbeat
- Phase 4: Memory consolidation, advanced providers

## Coding Style
- Use `from __future__ import annotations` in every file
- Type hints everywhere
- Async by default (asyncio)
- Logging via stdlib logging module
- No emojis in code or output
