# KIRA — Knowledge-driven Intelligent Reasoning Agent

A personal AI agent framework that runs on your own infrastructure, connects to any LLM provider, and genuinely self-improves through outcome-verified learning loops.

Built by combining the best architectural ideas from [Hermes Agent](https://github.com/nousresearch/hermes-agent) and [OpenClaw](https://github.com/openclaw/openclaw) — without their bloat, instability, or broken self-evaluation.

## What It Does

- Connects to **any LLM** — OpenRouter, OpenAI, Anthropic, Groq, Ollama, and any OpenAI-compatible endpoint
- **Manages your Gmail** — search, read, send, draft, label emails via the Gmail API
- **Self-improves** — learns from successful tasks, scores skills by verified outcomes, prunes what doesn't work
- **Runs anywhere** — your laptop, a $5 VPS, a Raspberry Pi, or any cloud provider
- **Stays small** — ~3,500 lines of Python. No LangChain, no LiteLLM, no heavyweight frameworks

## Quick Start

### 1. Install

```bash
git clone <your-repo-url> kira
cd kira
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

### 2. Configure Your LLM Provider

```bash
# Create the config directory
kira  # First run creates ~/.kira/ with default files

# Copy the example config
cp examples/settings.yaml ~/.kira/settings.yaml
cp examples/secrets.yaml ~/.kira/secrets.yaml
```

Edit `~/.kira/secrets.yaml` with your API key:

```yaml
OPENROUTER_API_KEY: "sk-or-your-key-here"
```

Edit `~/.kira/settings.yaml` to set your provider:

```yaml
providers:
  openrouter:
    type: openai_compatible
    base_url: https://openrouter.ai/api/v1
    api_key_env: OPENROUTER_API_KEY

routing:
  default: openrouter/anthropic/claude-sonnet-4-20250514
```

You can use **any provider** — OpenRouter gives you access to 200+ models with a single key.

### 3. Connect Gmail (Optional)

```bash
# One-time setup:
# 1. Go to https://console.cloud.google.com/
# 2. Create a project (or use existing)
# 3. Enable the Gmail API (APIs & Services > Library > search "Gmail API" > Enable)
# 4. Go to Credentials > Create Credentials > OAuth Client ID
# 5. Choose "Desktop app" as application type
# 6. Download the JSON file
# 7. Save it as ~/.kira/google_credentials.json

# Then authenticate:
kira setup google
```

This opens your browser for Google OAuth consent. Once authorized, Kira can manage your email.

### 4. Start Kira

```bash
kira
```

### 5. Talk to It

```
you> check my unread emails
you> read the email from John about the meeting
you> draft a reply saying I'll be 10 minutes late
you> search for emails from linkedin in the last week
you> archive all promotional emails from today
you> what files are in my home directory?
you> fetch the contents of https://news.ycombinator.com
```

## REPL Commands

| Command | Description |
|---------|-------------|
| `/new` | Start a new conversation session |
| `/sessions` | List recent sessions |
| `/search <query>` | Search past conversations (full-text) |
| `/cost` | Show current session token usage and cost |
| `/setup google` | Connect your Google account |
| `/gmail status` | Check Gmail connection |
| `/help` | Show all commands |
| `exit` | Quit |

## Built-in Tools

The agent has access to these tools and uses them automatically based on your requests:

| Tool | Description |
|------|-------------|
| `gmail_search` | Search Gmail with Gmail syntax (`is:unread`, `from:x`, etc.) |
| `gmail_read` | Read full email content |
| `gmail_send` | Send an email (requires your approval) |
| `gmail_draft` | Create a draft email |
| `gmail_label` | Add/remove labels (archive, star, etc.) |
| `gmail_list_labels` | List all Gmail labels |
| `terminal` | Run shell commands (requires approval) |
| `file_read` | Read file contents |
| `file_write` | Write/create files |
| `file_search` | Find files by glob pattern |
| `text_search` | Search text in files (grep) |
| `web_fetch` | Fetch and extract content from URLs |

## Configuring Providers

Kira supports any LLM provider. Add them to `~/.kira/settings.yaml`:

```yaml
providers:
  # OpenRouter — access 200+ models with one key
  openrouter:
    type: openai_compatible
    base_url: https://openrouter.ai/api/v1
    api_key_env: OPENROUTER_API_KEY

  # Direct Anthropic API
  anthropic:
    type: anthropic
    api_key_env: ANTHROPIC_API_KEY

  # Direct OpenAI
  openai:
    type: openai_compatible
    base_url: https://api.openai.com/v1
    api_key_env: OPENAI_API_KEY

  # Groq (fast inference)
  groq:
    type: openai_compatible
    base_url: https://api.groq.com/openai/v1
    api_key_env: GROQ_API_KEY

  # Local models via Ollama
  ollama:
    type: openai_compatible
    base_url: http://localhost:11434/v1
    api_key: "ollama"

  # Any OpenAI-compatible endpoint
  my_custom:
    type: openai_compatible
    base_url: https://my-server.example.com/v1
    api_key_env: CUSTOM_API_KEY

routing:
  # Default model for all requests
  default: openrouter/anthropic/claude-sonnet-4-20250514

  # Fallback if default fails
  fallback_chain:
    - openrouter/google/gemini-2.5-flash
    - ollama/llama3.1:8b

  # Route specific task types to cheaper/faster models
  task_routing:
    summarize: openrouter/google/gemini-2.5-flash
    code: openrouter/anthropic/claude-sonnet-4-20250514
```

## Self-Improving Skills

Kira learns from tasks it completes successfully. Unlike Hermes (which always thinks it did well), Kira uses **outcome-based verification** — it checks if the task actually succeeded before saving a skill.

Skills are plain markdown files in `~/.kira/skills/store/`:

```markdown
---
name: email-morning-triage
description: Triage morning inbox — flag urgent, archive newsletters
triggers: ["check email", "morning emails", "inbox triage"]
success_rate: 0.85
use_count: 12
---

# Steps
1. Search for unread emails from the last 12 hours
2. Categorize: urgent (from known contacts about deadlines),
   actionable (needs reply), informational (newsletters/updates)
3. Star urgent emails
4. Draft replies for actionable ones
5. Archive newsletters with a summary
```

The self-improvement loop:
1. Agent completes a task
2. Outcome is verified (did the files get created? did the email send? did the user approve?)
3. If verified success: skill is created or updated, success rate increases
4. If failure: logged but NOT saved as a skill
5. Skills below 30% success rate are auto-disabled

## Customizing Your Agent

### Identity (`~/.kira/SOUL.md`)

Define your agent's personality and behavior:

```markdown
# SOUL.md
You are Kira, a personal AI assistant for Anjali.

## Personality
- Direct and concise. No fluff.
- Proactive — suggest improvements when you see them.

## Domains
- Job searching and applications
- Email management
- Research and summarization
```

### Rules (`~/.kira/RULES.md`)

Hard constraints the agent must follow:

```markdown
# RULES.md
## Never Do
- Never send an email without explicit approval
- Never delete files without confirmation
```

### Memory (`~/.kira/MEMORY.md`)

Long-term knowledge that persists across sessions:

```markdown
# MEMORY.md
## Job Search
- [2026-04-20] Applied to Backend Engineer at Stripe. Status: pending.
```

## Adding Custom Tools

Drop a Python file in `~/.kira/tools/`:

```python
# ~/.kira/tools/stock_price.py
from kira.tools import Tool, ToolSchema, ToolResult, ToolContext, ToolRegistry

class StockPriceTool(Tool):
    schema = ToolSchema(
        name="stock_price",
        description="Check current stock price for a ticker symbol",
        parameters={
            "type": "object",
            "properties": {
                "ticker": {"type": "string", "description": "Stock ticker"}
            },
            "required": ["ticker"],
        },
    )

    async def execute(self, arguments, context):
        ticker = arguments["ticker"]
        # Your implementation here
        return ToolResult(success=True, output=f"{ticker}: $150.00")

def register(registry: ToolRegistry):
    registry.register(StockPriceTool())
```

It's auto-discovered on startup.

## Architecture

```
~/.kira/
  settings.yaml       — Configuration
  secrets.yaml        — API keys (chmod 600)
  SOUL.md             — Agent personality
  USER.md             — User profile
  RULES.md            — Hard constraints
  MEMORY.md           — Long-term knowledge
  HEARTBEAT.md        — Scheduled tasks (Phase 3)
  sessions.db         — Conversation history (SQLite + FTS5)
  google_credentials.json  — Google OAuth credentials
  google_token.json   — Google OAuth token (auto-managed)
  skills/store/       — Learned skills
  skills/archive/     — Disabled skills
  tools/              — Custom tools
  logs/kira.log       — Application log
```

## Requirements

- Python 3.9+
- 1 GB RAM, any OS (Linux, macOS, WSL2)
- An API key for at least one LLM provider

## License

MIT
