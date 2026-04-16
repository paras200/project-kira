# CLAUDE.md — Autonomous Workflow for KIRA

## Autonomy Rules
When the user asks you to build, fix, or enhance KIRA:
- **Do not ask clarifying questions.** Make reasonable decisions and proceed.
- **Do not ask for permission** to create files, install dependencies, or run tests.
- **Do not present options.** Pick the best one and build it.
- **Do not summarize what you will do.** Just do it.
- **After building, verify it works** by running imports and basic tests.
- **Commit when asked**, not before. Never push without being told to.
- If something is ambiguous, choose the simpler path. You can always iterate.

## Project Overview
KIRA (Knowledge-driven Intelligent Reasoning Agent) is a personal AI agent framework.
It combines the best ideas from Hermes Agent and OpenClaw into a lightweight, self-improving agent.
Python 3.9+. No heavy frameworks. Direct HTTP via httpx. All state is local (SQLite + markdown).

## Directory Structure
```
kira/
  core/             — Agent loop, providers, router, internal models
    providers/      — LLM adapters (openai_compat.py, anthropic_adapter.py)
    agent.py        — Main agent loop (prompt -> LLM -> tools -> repeat)
    router.py       — Model routing with fallback chain
    models.py       — Message, ToolCall, ToolSchema, TurnBudget, etc.
  identity/         — SOUL.md, USER.md, RULES.md loader
  skills/           — Skill loader, evaluator, store/
    evaluator.py    — Outcome-based skill scoring (never self-judgment)
    loader.py       — Skill discovery, selection, injection
  memory/           — Session DB (SQLite + FTS5)
  tools/            — Tool registry + built-in tools
    builtin/        — terminal, files, web, gmail
  channels/         — Messaging platform adapters (placeholder)
  scheduler/        — Cron/heartbeat (placeholder)
  config/           — Settings + secrets loader
  cli/              — REPL (repl.py) and entry point (main.py)
  web/              — Dashboard server (server.py) + UI (dashboard.html)
  integrations/     — Google OAuth2
```

## Running
```bash
source .venv/bin/activate
kira                    # CLI + dashboard at http://localhost:7777
kira serve              # Dashboard only (headless)
kira setup google       # Google OAuth
```

## Testing
```bash
source .venv/bin/activate
python -c "from kira.core.agent import Agent; print('OK')"
# Or run full import + tool + session + skill test:
python -c "
from kira.tools.registry import ToolRegistry
from kira.memory.sessions import SessionDB
from kira.skills.loader import SkillLoader
from kira.config.loader import build_kira_home
import tempfile, os
build_kira_home()
r = ToolRegistry(); r.load_builtin()
print(f'{len(r.list_schemas())} tools OK')
db = SessionDB(os.path.join(tempfile.mkdtemp(), 't.db'))
sid = db.create_session(); db.add_message(sid, 'user', 'test')
print(f'SessionDB OK')
db.close()
"
```

## Development Rules
- Keep codebase under 10,000 lines
- No LangChain, LiteLLM, LlamaIndex — direct httpx calls
- Every tool returns ToolResult(success, output, outcome)
- Provider adapters normalize to internal Message format
- Skills use OUTCOME-BASED verification, never LLM self-judgment
- Skills are markdown with YAML frontmatter in skills/store/
- New tools: create file in tools/builtin/, add register() function, auto-discovered
- New providers: if OpenAI-compatible, just add to settings.yaml. Otherwise extend ProviderAdapter.

## Key Patterns

### Adding a tool
```python
# kira/tools/builtin/my_tool.py
class MyTool(Tool):
    schema = ToolSchema(name="my_tool", description="...", parameters={...})
    async def execute(self, arguments, context) -> ToolResult:
        return ToolResult(success=True, output="result", outcome={"key": "val"})
def register(registry): registry.register(MyTool())
```

### Adding a provider
If OpenAI-compatible: just add to ~/.kira/settings.yaml. Otherwise:
```python
# kira/core/providers/my_provider.py — extend ProviderAdapter
# Then register in kira/cli/main.py _build_router()
```

## Phase Roadmap
- Phase 1 (DONE): Core agent, providers, tools, CLI, session DB
- Phase 1.5 (DONE): Gmail integration (search, read, send, draft, label)
- Phase 2 (DONE): Skills system with outcome-based self-improvement
- Phase 2.5 (DONE): Web dashboard (config, monitoring, activity, skills, identity editor)
- Phase 3 (NEXT): Telegram channel, scheduler/heartbeat
- Phase 4: Memory consolidation, Google Calendar, advanced providers

## Coding Style
- `from __future__ import annotations` in every file
- Type hints everywhere, async by default
- Logging via stdlib logging
- No emojis in code or output
- Minimal dependencies — if stdlib can do it, use stdlib
