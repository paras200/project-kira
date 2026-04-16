# KIRA — Personal AI Agent Framework

## Specification v1.0

**Kira**: Knowledge-driven Intelligent Reasoning Agent

---

## 1. Vision

Build a personal AI agent framework that:

- Runs 24/7 on your own infrastructure (any cloud, VPS, or local machine)
- Connects to any LLM provider (not locked to one)
- Genuinely self-improves through outcome-verified learning loops
- Handles personal tasks: email, job applications, research, scheduling, and more
- Stays small, hackable, and fully under your control
- Stays lightweight — no bloat from heavyweight agent frameworks

**Non-goals**: We are NOT building a product for others. No marketplace, no plugin store, no mobile apps. This is YOUR agent, YOUR rules.

---

## 2. Design Principles

1. **Simplicity over features.** Start with 5,000 lines, not 400,000. Add complexity only when earned.
2. **Outcome-based learning.** The agent never judges itself. Success is measured by verifiable outcomes.
3. **Provider-agnostic.** Swap models mid-conversation if needed. No SDK lock-in.
4. **Config-as-markdown.** Identity, skills, memory, heartbeat — all plain markdown files you can edit in any text editor.
5. **Modular channels.** Each messaging platform is a self-contained adapter. Add or remove without touching core.
6. **Fail loudly.** No silent degradation. If something breaks, you know immediately.
7. **Your data stays yours.** All state is local files + SQLite. No external services required (unless you choose to add them).

---

## 3. Architecture Overview

```
kira/
  core/                    — The brain
    agent.py               — Agent loop (prompt -> LLM -> tools -> repeat)
    providers/             — LLM provider adapters
    compressor.py          — Context window management
    router.py              — Model routing and fallback logic

  identity/                — Who the agent is
    SOUL.md                — Agent personality and behavior rules
    USER.md                — What the agent knows about you
    RULES.md               — Hard constraints the agent must follow

  skills/                  — Learned capabilities
    loader.py              — Discover and inject skills
    evaluator.py           — Outcome-based skill scoring
    store/                 — Skill markdown files (auto-created and manual)

  memory/                  — What the agent remembers
    sessions.py            — Conversation history (SQLite + FTS5)
    long_term.py           — Persistent knowledge (MEMORY.md)
    consolidator.py        — Background memory distillation

  tools/                   — What the agent can do
    registry.py            — Tool registration and dispatch
    builtin/               — Built-in tools (terminal, files, browser, etc.)
    custom/                — Your custom tools

  channels/                — Where the agent listens
    base.py                — Channel adapter interface
    telegram.py            — Telegram adapter
    email.py               — Email adapter (IMAP/SMTP)
    api.py                 — REST API for custom integrations

  scheduler/               — When the agent acts
    cron.py                — Cron-based job scheduling
    HEARTBEAT.md           — Recurring task definitions

  config/                  — How the agent is configured
    settings.yaml          — Runtime configuration
    secrets.yaml           — API keys and credentials (gitignored)

  cli/                     — How you interact locally
    main.py                — CLI entry point
    repl.py                — Interactive REPL

  web/                     — Dashboard (Phase 3)
    dashboard.py           — Simple web UI for monitoring
```

---

## 4. Provider System

### 4.1 Goal

Support ANY LLM that exposes a chat completions-compatible API. No dependency on any specific SDK. The provider system is a thin adapter layer that normalizes different APIs into a single internal format.

### 4.2 Supported Providers

| Provider | API Format | Auth | Notes |
|----------|-----------|------|-------|
| OpenRouter | OpenAI-compatible | Bearer token | Aggregator — access to 200+ models |
| OpenAI | OpenAI Chat Completions | Bearer token | GPT-4o, o3, etc. |
| Anthropic | Anthropic Messages API | x-api-key header | Claude Opus, Sonnet, Haiku |
| Google Gemini | Google GenAI / OpenAI-compatible | Bearer token or API key | Gemini 2.5 Pro/Flash |
| AWS Bedrock | Bedrock Converse API | AWS SigV4 | Claude, Llama, etc. via AWS |
| Azure OpenAI | OpenAI-compatible | Bearer token or API key | GPT models via Azure |
| Ollama | OpenAI-compatible | None (local) | Local models |
| LM Studio | OpenAI-compatible | None (local) | Local models |
| Together AI | OpenAI-compatible | Bearer token | Open-source models |
| Groq | OpenAI-compatible | Bearer token | Fast inference |
| Fireworks AI | OpenAI-compatible | Bearer token | Fast inference |
| Mistral | OpenAI-compatible + native | Bearer token | Mistral models |
| DeepSeek | OpenAI-compatible | Bearer token | DeepSeek models |
| Any OpenAI-compatible | OpenAI-compatible | Configurable | Custom/self-hosted endpoints |

### 4.3 Internal Message Format

All providers normalize to this internal format:

```python
@dataclass
class Message:
    role: str                      # "system" | "user" | "assistant" | "tool"
    content: str | list[Content]   # Text or multimodal content blocks
    tool_calls: list[ToolCall] | None
    tool_call_id: str | None       # For tool result messages
    name: str | None               # Tool name for tool results
    metadata: dict | None          # Provider-specific passthrough

@dataclass
class Content:
    type: str          # "text" | "image_url" | "image_base64"
    text: str | None
    image_url: str | None
    image_base64: str | None
    media_type: str | None

@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict

@dataclass
class CompletionResponse:
    message: Message
    usage: Usage                   # prompt_tokens, completion_tokens, total_tokens
    model: str                     # Actual model used
    finish_reason: str             # "stop" | "tool_calls" | "length"
    cost: float | None             # Estimated cost in USD
    latency_ms: int                # Request latency
    provider: str                  # Which provider served this
    raw: dict | None               # Raw provider response for debugging
```

### 4.4 Provider Adapter Interface

```python
class ProviderAdapter(ABC):
    """Base class for all LLM provider adapters."""

    name: str                          # e.g., "openai", "anthropic", "ollama"
    supports_streaming: bool
    supports_tool_calls: bool
    supports_vision: bool
    supports_system_prompt: bool       # Some models don't support system role

    @abstractmethod
    async def complete(
        self,
        messages: list[Message],
        tools: list[ToolSchema] | None,
        model: str,
        temperature: float,
        max_tokens: int | None,
        stop: list[str] | None,
    ) -> CompletionResponse:
        """Send a completion request and return the full response."""

    @abstractmethod
    async def stream(
        self,
        messages: list[Message],
        tools: list[ToolSchema] | None,
        model: str,
        temperature: float,
        max_tokens: int | None,
        stop: list[str] | None,
    ) -> AsyncIterator[StreamChunk]:
        """Stream a completion response chunk by chunk."""

    @abstractmethod
    def normalize_messages(self, messages: list[Message]) -> list[dict]:
        """Convert internal messages to provider-specific format."""

    @abstractmethod
    def parse_response(self, raw: dict) -> CompletionResponse:
        """Convert provider response to internal format."""

    def estimate_cost(self, model: str, usage: Usage) -> float | None:
        """Estimate cost based on known pricing. Returns None if unknown."""
```

### 4.5 Provider Categories

We handle three distinct API shapes:

**Category A — OpenAI-compatible** (OpenRouter, OpenAI, Azure, Groq, Together, Fireworks, Ollama, LM Studio, DeepSeek, Mistral):
- Single adapter class: `OpenAICompatibleAdapter`
- Constructor takes: `base_url`, `api_key`, `default_headers`
- Covers ~80% of providers with zero custom code

**Category B — Anthropic Messages API**:
- Custom adapter: `AnthropicAdapter`
- Handles: system prompt as separate field, content blocks format, tool_use/tool_result roles

**Category C — AWS Bedrock Converse API**:
- Custom adapter: `BedrockAdapter`
- Handles: SigV4 auth, Converse API format, model ID mapping

**Category D — Google GenAI**:
- Custom adapter: `GoogleAdapter`
- Handles: Google auth, GenerateContent format, function calling format
- Note: Gemini also supports OpenAI-compatible mode — user can choose either

### 4.6 Model Router

The router decides which provider+model to use for each request.

```python
class ModelRouter:
    """Routes requests to the appropriate provider and model."""

    def __init__(self, config: RouterConfig):
        self.providers: dict[str, ProviderAdapter] = {}
        self.default_model: ModelSpec = config.default_model
        self.fallback_chain: list[ModelSpec] = config.fallback_chain
        self.task_routing: dict[str, ModelSpec] = config.task_routing

    async def complete(self, messages, tools, task_hint=None, **kwargs):
        """
        Route to the best provider/model for this request.

        Routing priority:
        1. Explicit model override in kwargs
        2. Task-specific routing (e.g., "summarize" -> cheap model)
        3. Default model
        4. Fallback chain on failure
        """

    def add_provider(self, name: str, adapter: ProviderAdapter, models: list[str]):
        """Register a provider with its available models."""
```

### 4.7 Configuration Example

```yaml
# settings.yaml — providers section
providers:
  openrouter:
    type: openai_compatible
    base_url: https://openrouter.ai/api/v1
    api_key_env: OPENROUTER_API_KEY        # Read from secrets.yaml or env var
    default_headers:
      HTTP-Referer: "https://github.com/paras200/project-kira"
    models:
      - anthropic/claude-sonnet-4-20250514
      - google/gemini-2.5-flash
      - deepseek/deepseek-chat
      - meta-llama/llama-4-maverick

  anthropic:
    type: anthropic
    api_key_env: ANTHROPIC_API_KEY
    models:
      - claude-sonnet-4-20250514
      - claude-haiku-4-5-20251001

  ollama:
    type: openai_compatible
    base_url: http://localhost:11434/v1
    api_key: "ollama"                       # Ollama doesn't need a real key
    models:
      - llama3.1:8b
      - qwen2.5-coder:7b

  openai:
    type: openai_compatible
    base_url: https://api.openai.com/v1
    api_key_env: OPENAI_API_KEY
    models:
      - gpt-4o
      - gpt-4o-mini

  groq:
    type: openai_compatible
    base_url: https://api.groq.com/openai/v1
    api_key_env: GROQ_API_KEY
    models:
      - llama-3.3-70b-versatile
      - gemma2-9b-it

  bedrock:
    type: bedrock
    region: us-east-1
    # Uses AWS credentials from environment/profile
    models:
      - anthropic.claude-sonnet-4-20250514-v1:0
      - meta.llama3-1-70b-instruct-v1:0

  google:
    type: google
    api_key_env: GOOGLE_API_KEY
    models:
      - gemini-2.5-pro
      - gemini-2.5-flash

  custom_endpoint:
    type: openai_compatible
    base_url: https://my-vllm-server.example.com/v1
    api_key_env: CUSTOM_API_KEY
    models:
      - my-finetuned-model

# Model routing
routing:
  default: openrouter/anthropic/claude-sonnet-4-20250514
  
  fallback_chain:
    - openrouter/google/gemini-2.5-flash
    - ollama/llama3.1:8b

  task_routing:
    summarize: openrouter/google/gemini-2.5-flash        # Cheap model for summaries
    code: openrouter/anthropic/claude-sonnet-4-20250514   # Best model for code
    chat: openrouter/deepseek/deepseek-chat               # Balanced for chat
    classify: groq/gemma2-9b-it                           # Fast model for classification
    embed: openai/text-embedding-3-small                  # Embeddings
```

---

## 5. Agent Loop

### 5.1 Core Loop

The agent loop is intentionally simple. No 14,700-line monolith.

```
User message arrives (from CLI, Telegram, email, API, or cron job)
    |
    v
[1] Build system prompt
    - Load SOUL.md (identity)
    - Load USER.md (user profile)
    - Load RULES.md (hard constraints)
    - Load active skills (filtered by relevance)
    - Load recent memory context
    - Load tool schemas
    |
    v
[2] Send to LLM (via Model Router)
    - Messages: system + conversation history + new user message
    - Tools: active tool schemas
    - Stream response
    |
    v
[3] Parse response
    - If text-only response -> return to user, go to [6]
    - If tool calls -> go to [4]
    |
    v
[4] Execute tool calls
    - Validate tool call against schema
    - Check against RULES.md constraints
    - Execute tool handler
    - Capture result (stdout, stderr, return value)
    - Capture outcome metadata (did the email send? did the file write? etc.)
    - Append tool results to conversation
    - Go to [2] (loop back to LLM with results)
    |
    v
[5] Loop guard
    - Max iterations per conversation turn: configurable (default: 25)
    - Token budget per turn: configurable
    - If budget exceeded -> force text response, warn user
    |
    v
[6] Post-turn processing
    - Save conversation to session DB
    - Run skill evaluator (async, non-blocking)
    - Update memory if significant new knowledge
    - Log cost and latency metrics
```

### 5.2 Iteration Budget

```python
@dataclass
class TurnBudget:
    max_iterations: int = 25           # Max tool call rounds per turn
    max_input_tokens: int = 100_000    # Max tokens sent to LLM across all iterations
    max_output_tokens: int = 16_000    # Max tokens generated per iteration
    max_cost_usd: float = 1.00         # Max cost per turn
    current_iterations: int = 0
    current_input_tokens: int = 0
    current_cost: float = 0.0

    def is_exhausted(self) -> bool:
        return (
            self.current_iterations >= self.max_iterations
            or self.current_input_tokens >= self.max_input_tokens
            or self.current_cost >= self.max_cost_usd
        )
```

### 5.3 Context Window Management

When the conversation history approaches the model's context limit:

1. **Measure**: Count tokens in the full message list (use tiktoken for OpenAI-compat, or provider-specific tokenizers)
2. **Threshold**: If >60% of context window used, trigger compression
3. **Compress**: 
   - Keep first 3 messages (system prompt + initial context) intact
   - Summarize middle messages using a cheap/fast model (task_routing: summarize)
   - Keep last N messages (recent context) intact
   - Replace old tool results with one-line summaries
4. **Anti-thrash**: Skip compression if last compression saved <10% of tokens

---

## 6. Identity System

### 6.1 SOUL.md

Defines WHO the agent is. Loaded as part of the system prompt.

```markdown
# SOUL.md

You are Kira, a personal AI assistant for [Your Name].

## Personality
- Direct and concise. No fluff.
- Proactive — suggest improvements, don't wait to be asked.
- Honest about limitations. Say "I don't know" rather than guessing.

## Communication Style
- Default to short responses unless asked for detail.
- Use bullet points over paragraphs.
- Never use emojis unless explicitly asked.

## Core Behaviors
- Always confirm before taking irreversible actions (sending emails, deleting files).
- When a task is ambiguous, ask ONE clarifying question, not five.
- Prefer doing over discussing. If you can just do it, do it.

## Domains
- Job searching and applications
- Email management and drafting
- Research and summarization
- Scheduling and reminders
- Code and automation tasks
```

### 6.2 USER.md

What the agent knows about you. Updated by the agent (with your approval) and by you manually.

```markdown
# USER.md

## Profile
- Name: [Your Name]
- Role: Software Engineer
- Location: [Your City], [Timezone]
- Primary language: English

## Preferences
- Prefers morning briefings at 8:00 AM
- Likes research summaries with sources cited
- Job search focus: Backend/ML engineering roles, remote preferred
- Email: check twice daily, flag urgent, draft replies for review

## Communication
- Telegram for quick updates
- Email for detailed reports
- Never call unless emergency

## Context
- Currently job searching (started April 2026)
- Self-hosting the agent on own infrastructure
- Interested in AI/ML and distributed systems
```

### 6.3 RULES.md

Hard constraints that the agent MUST follow. These override everything, including skills.

```markdown
# RULES.md — Hard Constraints

## Never Do
- Never send an email without explicit approval
- Never delete files without confirmation
- Never share personal information with external services
- Never spend more than $0.50 on a single task without asking
- Never execute commands with `rm -rf`, `DROP TABLE`, or destructive equivalents
- Never access files outside the designated workspace

## Always Do
- Always log tool executions with timestamps
- Always show cost after expensive operations
- Always save drafts before sending any communication
- Always cite sources in research summaries

## Security
- Never include API keys, passwords, or tokens in responses
- Never make requests to URLs not in the approved domain list
- Never execute code from untrusted sources without sandboxing
```

---

## 7. Skill System

### 7.1 What is a Skill

A skill is a markdown file that teaches the agent HOW to do a specific task. Skills are:
- Created manually by you, OR
- Created by the agent after successfully completing a task (with outcome verification)
- Injected into the system prompt when relevant
- Scored based on verified success rate
- Pruned or disabled when they degrade performance

### 7.2 Skill Format

```markdown
---
name: job-application-linkedin
description: Apply to jobs on LinkedIn using saved profile and cover letter templates
category: job-search
triggers:
  - "apply to job"
  - "linkedin application"
  - "submit application"
requires_tools:
  - browser
  - file_read
created_by: agent | manual
created_at: 2026-04-20T10:30:00Z
last_used: 2026-04-25T14:00:00Z
use_count: 12
success_count: 10
success_rate: 0.83
version: 3
status: active                         # active | disabled | under_review
---

# How to Apply to Jobs on LinkedIn

## Steps
1. Read the job description carefully
2. Load the user's resume from `~/documents/resume.pdf`
3. Load the cover letter template from `~/documents/cover_letter_template.md`
4. Customize the cover letter based on the job description
5. Save the customized cover letter as `~/documents/applications/{company}_{date}.md`
6. Present the customized cover letter to the user for approval
7. WAIT for user approval before proceeding
8. Navigate to the LinkedIn job posting
9. Fill in the application form
10. Upload resume and cover letter
11. Submit the application
12. Log the application in `~/documents/job_tracker.csv`

## Success Criteria
- Application submitted confirmation received
- Cover letter saved to applications folder
- Job tracker updated with: company, role, date, status

## Known Pitfalls
- LinkedIn sometimes requires re-authentication mid-flow
- Some job postings redirect to external ATS — handle gracefully
- Always check if "Easy Apply" is available vs full application

## Revision History
- v1: Initial skill (manual)
- v2: Added cover letter customization step (agent-learned)
- v3: Added job tracker logging (agent-learned, verified 3x)
```

### 7.3 Skill Lifecycle

```
[Create]
    Manual: You write a SKILL.md and drop it in skills/store/
    Agent-created: After a verified successful task completion
    |
    v
[Activate]
    Skill loader scans store/ at startup and on file change
    Skills are indexed by name, triggers, and category
    Relevance matching: skill triggers vs. user message (keyword + embedding similarity)
    |
    v
[Use]
    Relevant skills are injected into the system prompt for the current turn
    Max skills per turn: 3 (configurable) to avoid context pollution
    Skills are injected as user messages (not system) to avoid cache invalidation
    |
    v
[Evaluate] — THE KEY DIFFERENTIATOR
    After task completion, the evaluator checks:
    1. Were the success criteria met? (parsed from the skill's "Success Criteria")
    2. Did the tools produce the expected outcomes? (file created? email sent? etc.)
    3. Did the user accept the result or reject/correct it?
    
    Scoring:
    - Verified success: success_count += 1
    - Verified failure: failure logged, skill flagged for review
    - User correction: skill updated with the correction, version bumped
    - User rejection: skill NOT updated, failure logged
    |
    v
[Improve]
    When a skill succeeds but the agent took a DIFFERENT approach than documented:
    - Diff the actual steps vs. documented steps
    - If the new approach was faster/cheaper: propose skill update
    - Update requires: 2 consecutive verified successes with the new approach
    - Old version is kept as `SKILL.md.v{N}.bak` for rollback
    |
    v
[Prune]
    Skills with success_rate < 0.3 after 5+ uses: auto-disabled
    Skills unused for 90 days: flagged for review
    Skills that increase token cost >30% vs. baseline: flagged
    Disabled skills are moved to skills/archive/, not deleted
```

### 7.4 Skill Injection Strategy

NOT all skills are loaded into every conversation. That causes context pollution.

```python
class SkillLoader:
    MAX_SKILLS_PER_TURN = 3
    MAX_SKILL_TOKENS = 2000            # Per skill, truncate if longer
    MAX_TOTAL_SKILL_TOKENS = 5000      # Total skill budget per turn

    def select_skills(self, user_message: str, active_skills: list[Skill]) -> list[Skill]:
        """
        Select the most relevant skills for this message.

        Relevance scoring:
        1. Trigger keyword match (exact or fuzzy) — weight: 0.5
        2. Category match — weight: 0.2
        3. Success rate — weight: 0.2
        4. Recency of last use — weight: 0.1

        Returns top MAX_SKILLS_PER_TURN skills above relevance threshold.
        """
```

---

## 8. Self-Improving Loop (Outcome-Based)

### 8.1 Why Self-Evaluation Fails

Letting the agent self-evaluate ("Did I do a good job?") always results in positive ratings. This creates a feedback loop where bad skills accumulate and good skills get overwritten.

### 8.2 Our Approach: Outcome Verification

The agent NEVER judges its own performance. Instead:

```
Task Execution
    |
    v
Outcome Capture
    - What files were created/modified? (checksums, sizes)
    - What API calls returned success/failure?
    - What was the user's reaction? (approved / rejected / corrected / no response)
    - How many tokens/dollars were spent?
    - How many iterations did it take?
    |
    v
Success Criteria Check (from skill's YAML frontmatter or task definition)
    - Each criterion is a verifiable assertion:
      - "file_exists: ~/documents/applications/{company}_{date}.md"
      - "csv_row_added: ~/documents/job_tracker.csv"
      - "email_sent: true"
      - "user_approved: true"
    - Criteria are checked programmatically, not by the LLM
    |
    v
Score Update
    - All criteria met + user approved → SUCCESS
    - Some criteria met + user approved → PARTIAL (flag for skill review)
    - User rejected or corrected → FAILURE (do not update skill)
    - User corrected and re-approved → SUCCESS + update skill with correction
    |
    v
Skill Evolution (only on SUCCESS)
    - If agent deviated from skill steps and still succeeded:
      - Record the deviation
      - After 2 consecutive successes with same deviation: propose skill update
    - If agent followed skill exactly: increment success_count
    - Track cost_per_success trend — flag if it increases
```

### 8.3 Evaluation Config

```yaml
# settings.yaml — evaluation section
evaluation:
  auto_create_skills: true              # Agent can create new skills after verified success
  require_approval_for_new_skills: true # You must approve new agent-created skills
  require_approval_for_updates: false   # Auto-update on 2 consecutive successes
  min_successes_for_update: 2           # Consecutive successes before auto-updating
  disable_threshold: 0.3               # Disable skills below this success rate
  disable_min_uses: 5                   # Don't disable until N uses
  archive_after_days: 90               # Archive unused skills after N days
  max_skill_tokens: 2000               # Truncate skills longer than this
  max_skills_per_turn: 3               # Don't inject more than N skills
```

---

## 9. Memory System

### 9.1 Three Layers

**Layer 1 — Session Memory (Short-term)**
- Current conversation history
- Stored in-memory during conversation, persisted to SQLite on turn end
- Full-text searchable via FTS5
- Auto-compressed when context window fills up

**Layer 2 — Knowledge Memory (Long-term)**
- Persistent facts, preferences, and learned information
- Stored in `MEMORY.md` (simple, human-readable, version-controlled)
- Structured as categorized entries with timestamps
- Agent can propose additions; you approve or auto-approve based on config

**Layer 3 — Consolidated Memory (Background)**
- Periodic background process that reviews recent sessions
- Extracts patterns, recurring topics, and useful context
- Distills into knowledge memory entries
- Runs on a cheap model (e.g., Gemini Flash) to save costs
- Background consolidation with explicit verification

### 9.2 Session DB Schema

```sql
CREATE TABLE sessions (
    id TEXT PRIMARY KEY,
    title TEXT,
    channel TEXT,                        -- "cli" | "telegram" | "email" | "api" | "cron"
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    message_count INTEGER DEFAULT 0,
    total_tokens INTEGER DEFAULT 0,
    total_cost_usd REAL DEFAULT 0.0,
    model TEXT,
    metadata JSON
);

CREATE TABLE messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT REFERENCES sessions(id),
    role TEXT NOT NULL,                   -- "system" | "user" | "assistant" | "tool"
    content TEXT,
    tool_calls JSON,                     -- Serialized tool calls
    tool_call_id TEXT,
    tool_name TEXT,
    tokens INTEGER,
    cost_usd REAL,
    model TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE VIRTUAL TABLE messages_fts USING fts5(
    content,
    content=messages,
    content_rowid=id
);

CREATE TABLE skill_evaluations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT REFERENCES sessions(id),
    skill_name TEXT,
    outcome TEXT,                         -- "success" | "partial" | "failure"
    criteria_results JSON,               -- { criterion: true/false }
    user_feedback TEXT,                   -- "approved" | "rejected" | "corrected" | null
    tokens_used INTEGER,
    cost_usd REAL,
    iterations INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### 9.3 MEMORY.md Format

```markdown
# MEMORY.md — Long-term Knowledge

## Job Search
- [2026-04-20] Applied to Backend Engineer at Stripe. Status: pending.
- [2026-04-22] Applied to ML Engineer at Databricks. Status: phone screen scheduled 2026-04-28.
- [2026-04-25] Preference: avoid companies requiring >3 interview rounds.

## Email Patterns
- [2026-04-18] Boss sends weekly sync requests on Mondays — auto-accept.
- [2026-04-20] Newsletter from TechCrunch — auto-archive, summarize weekly.

## Technical Notes
- [2026-04-19] Current server has 1GB RAM — avoid memory-heavy tasks.
- [2026-04-21] OpenRouter rate limits: 200 req/min for free tier.

## Personal
- [2026-04-16] User prefers morning briefings at 8:00 AM IST.
- [2026-04-18] User's resume is at ~/documents/resume.pdf, last updated 2026-04-15.
```

### 9.4 Memory Consolidation

```python
class MemoryConsolidator:
    """
    Background process that reviews recent sessions and extracts
    useful knowledge into MEMORY.md.

    Runs: Every 6 hours (configurable)
    Model: Uses the cheapest available model (task_routing: summarize)
    """

    async def consolidate(self):
        # 1. Load sessions from last consolidation window
        # 2. Load current MEMORY.md
        # 3. Ask LLM: "What new facts, preferences, or patterns
        #    from these sessions should be added to long-term memory?
        #    Do NOT add anything already present. Be concise."
        # 4. Parse proposed additions
        # 5. If auto_approve: append to MEMORY.md
        #    If not: queue for user review
        # 6. Update consolidation timestamp
```

### 9.5 Memory Config

```yaml
# settings.yaml — memory section
memory:
  session_db: ~/.kira/sessions.db
  memory_file: ~/.kira/MEMORY.md
  max_memory_entries: 200              # Prune oldest entries beyond this
  consolidation_interval_hours: 6
  consolidation_model: summarize       # Uses task_routing key
  auto_approve_memory: false           # Require user approval for new entries
  session_search_results: 5            # Max past sessions to include as context
  session_search_threshold: 0.3        # Minimum relevance score for session recall
```

---

## 10. Tool System

### 10.1 Tool Interface

```python
@dataclass
class ToolSchema:
    name: str
    description: str
    parameters: dict                    # JSON Schema
    requires_approval: bool = False     # Ask user before executing
    timeout_seconds: int = 30
    category: str = "general"

class Tool(ABC):
    schema: ToolSchema

    @abstractmethod
    async def execute(self, arguments: dict, context: ToolContext) -> ToolResult:
        """Execute the tool and return the result."""

    def validate(self, arguments: dict) -> bool:
        """Validate arguments against schema. Default: jsonschema validation."""

@dataclass
class ToolResult:
    success: bool
    output: str                         # Text output for the LLM
    outcome: dict | None = None         # Structured outcome for skill evaluation
    # Example outcome: {"file_created": "/path/to/file", "rows_added": 1}

@dataclass
class ToolContext:
    session_id: str
    user_id: str
    workspace: str                      # Working directory
    rules: list[str]                    # From RULES.md — constraints to check
    approve_callback: Callable | None   # For tools requiring approval
```

### 10.2 Tool Registry

```python
class ToolRegistry:
    """Self-registering tool catalog."""

    def __init__(self):
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool):
        self._tools[tool.schema.name] = tool

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def list_schemas(self, categories: list[str] | None = None) -> list[ToolSchema]:
        """Return schemas for active tools, optionally filtered by category."""

    async def execute(self, name: str, arguments: dict, context: ToolContext) -> ToolResult:
        tool = self.get(name)
        if tool is None:
            return ToolResult(success=False, output=f"Unknown tool: {name}")
        if not tool.validate(arguments):
            return ToolResult(success=False, output=f"Invalid arguments for {name}")
        if tool.schema.requires_approval and context.approve_callback:
            approved = await context.approve_callback(name, arguments)
            if not approved:
                return ToolResult(success=False, output="User denied tool execution")
        return await asyncio.wait_for(
            tool.execute(arguments, context),
            timeout=tool.schema.timeout_seconds
        )
```

### 10.3 Built-in Tools

**Phase 1 (MVP)**:

| Tool | Description | Approval Required |
|------|-------------|-------------------|
| `terminal` | Execute shell commands | Yes (configurable allowlist) |
| `file_read` | Read file contents | No |
| `file_write` | Write/create files | No |
| `file_search` | Search files by name pattern (glob) | No |
| `text_search` | Search file contents (grep) | No |
| `web_fetch` | Fetch a URL and extract text content | No |
| `web_search` | Search the web (via SearXNG, Brave, or Google) | No |

**Phase 2**:

| Tool | Description | Approval Required |
|------|-------------|-------------------|
| `browser` | Full browser automation (Playwright) | No |
| `email_read` | Read emails via IMAP | No |
| `email_send` | Send email via SMTP | Yes |
| `email_draft` | Save email draft | No |
| `calendar_read` | Read calendar events | No |
| `calendar_create` | Create calendar events | Yes |

**Phase 3**:

| Tool | Description | Approval Required |
|------|-------------|-------------------|
| `telegram_send` | Send Telegram message | Yes (first time, then auto) |
| `spreadsheet` | Read/write CSV and spreadsheet files | No |
| `pdf_read` | Extract text from PDFs | No |
| `image_describe` | Describe image contents (vision) | No |
| `code_execute` | Execute Python code in sandbox | No |

### 10.4 Custom Tools

Users can add custom tools by dropping a Python file in `tools/custom/`:

```python
# tools/custom/my_tool.py
from kira.tools import Tool, ToolSchema, ToolResult, ToolContext

class MyCustomTool(Tool):
    schema = ToolSchema(
        name="check_stock_price",
        description="Check the current stock price for a given ticker symbol",
        parameters={
            "type": "object",
            "properties": {
                "ticker": {"type": "string", "description": "Stock ticker symbol"}
            },
            "required": ["ticker"]
        },
        timeout_seconds=10,
        category="finance"
    )

    async def execute(self, arguments: dict, context: ToolContext) -> ToolResult:
        ticker = arguments["ticker"]
        # Your implementation here
        price = await fetch_stock_price(ticker)
        return ToolResult(
            success=True,
            output=f"{ticker} is currently at ${price}",
            outcome={"ticker": ticker, "price": price}
        )
```

Auto-discovered on startup. No registration boilerplate needed.

---

## 11. Channel System

### 11.1 Channel Adapter Interface

```python
class ChannelAdapter(ABC):
    """Base class for messaging platform adapters."""

    name: str                           # "telegram" | "email" | "api" | "cli"
    supports_streaming: bool
    supports_media: bool
    supports_approval: bool             # Can prompt user for yes/no

    @abstractmethod
    async def start(self):
        """Start listening for messages."""

    @abstractmethod
    async def stop(self):
        """Stop listening and clean up."""

    @abstractmethod
    async def send(self, channel_id: str, message: str, media: list | None = None):
        """Send a message to a specific channel/chat."""

    @abstractmethod
    async def on_message(self, callback: Callable[[IncomingMessage], Awaitable[None]]):
        """Register a callback for incoming messages."""

    async def request_approval(self, channel_id: str, action: str, details: str) -> bool:
        """Ask user to approve an action. Default: auto-approve."""
        return True

@dataclass
class IncomingMessage:
    channel: str                        # "telegram" | "email" | etc.
    channel_id: str                     # Chat/thread/inbox ID
    sender: str                         # User identifier
    text: str
    media: list | None = None           # Attached files/images
    reply_to: str | None = None         # If replying to a previous message
    metadata: dict | None = None        # Platform-specific data
    timestamp: datetime = field(default_factory=datetime.now)
```

### 11.2 Planned Channels

| Channel | Phase | Library | Notes |
|---------|-------|---------|-------|
| CLI (REPL) | 1 | prompt_toolkit | Local interactive mode |
| REST API | 1 | aiohttp | Webhook/HTTP integration |
| Telegram | 1 | python-telegram-bot | Primary mobile interface |
| Email (IMAP/SMTP) | 2 | aiosmtplib + aioimaplib | Read + send with approval |
| Discord | 3 | discord.py | If needed |
| Slack | 3 | slack-sdk | If needed |
| WhatsApp | 3 | via Telegram bridge or Baileys | Complex setup |

### 11.3 Channel Routing

When the agent needs to reach you, it picks the right channel:

```yaml
# settings.yaml — channel routing
channel_routing:
  urgent: telegram                      # Urgent messages go to Telegram
  reports: email                        # Daily reports go to email
  approvals: telegram                   # Approval requests go to Telegram
  default: telegram                     # Everything else
```

---

## 12. Scheduler System

### 12.1 HEARTBEAT.md

```markdown
# HEARTBEAT.md — Recurring Tasks

## Morning Briefing
- interval: daily 08:00
- channel: telegram
- prompt: >
    Check my email inbox for urgent messages. Summarize the top 5.
    Check my calendar for today's events. List them.
    Check for new job postings matching my saved search criteria.
    Send me a briefing on Telegram.

## Job Search Check
- interval: every 4 hours
- channel: telegram
- prompt: >
    Search for new Backend Engineer and ML Engineer job postings
    on the job boards I've configured. Only notify me if there are
    new postings since last check. Include: company, role, location,
    salary range if available.

## Email Cleanup
- interval: daily 20:00
- channel: email
- prompt: >
    Review today's unread non-urgent emails.
    Draft replies for any that need a response.
    Archive newsletters and promotional emails.
    Send me a summary of what was archived and what needs attention.

## Weekly Review
- interval: weekly monday 09:00
- channel: email
- prompt: >
    Compile a weekly review:
    - Job applications sent this week and their statuses
    - Important emails and their outcomes
    - Tasks completed
    - Upcoming calendar events for the week
    Send as a formatted email.
```

### 12.2 Cron Engine

```python
class Scheduler:
    """Parses HEARTBEAT.md and runs tasks on schedule."""

    def __init__(self, heartbeat_path: str, agent: Agent):
        self.tasks: list[ScheduledTask] = []
        self.agent = agent

    def load(self):
        """Parse HEARTBEAT.md into ScheduledTask objects."""

    async def run(self):
        """Main scheduler loop. Checks due tasks every 60 seconds."""
        while True:
            for task in self.tasks:
                if task.is_due():
                    asyncio.create_task(self._execute_task(task))
                    task.mark_executed()
            await asyncio.sleep(60)

    async def _execute_task(self, task: ScheduledTask):
        """Execute a scheduled task as a new agent session."""
        session = self.agent.create_session(
            channel=task.channel,
            source="scheduler",
            title=f"[Scheduled] {task.name}"
        )
        result = await self.agent.run(session, task.prompt)
        # Route result to the specified channel
        await self.agent.channels[task.channel].send(
            channel_id=task.channel_target,
            message=result
        )

@dataclass
class ScheduledTask:
    name: str
    interval: str                       # "daily 08:00" | "every 4 hours" | "weekly monday 09:00"
    channel: str
    prompt: str
    last_run: datetime | None = None
    enabled: bool = True

    def is_due(self) -> bool:
        """Check if this task should run now based on interval and last_run."""
```

---

## 13. Configuration

### 13.1 settings.yaml (Full Reference)

```yaml
# ~/.kira/settings.yaml

# --- Agent Identity ---
identity:
  soul: ~/.kira/SOUL.md
  user: ~/.kira/USER.md
  rules: ~/.kira/RULES.md

# --- Providers (see Section 4.7 for full examples) ---
providers:
  # ... provider configs ...

# --- Model Routing ---
routing:
  default: openrouter/anthropic/claude-sonnet-4-20250514
  fallback_chain:
    - openrouter/google/gemini-2.5-flash
    - ollama/llama3.1:8b
  task_routing:
    summarize: openrouter/google/gemini-2.5-flash
    code: openrouter/anthropic/claude-sonnet-4-20250514
    classify: groq/gemma2-9b-it

# --- Agent Loop ---
agent:
  max_iterations: 25
  max_input_tokens: 100000
  max_output_tokens: 16000
  max_cost_per_turn: 1.00
  temperature: 0.7
  compression_threshold: 0.6          # Compress at 60% context usage

# --- Skills ---
skills:
  store: ~/.kira/skills/
  archive: ~/.kira/skills/archive/
  max_per_turn: 3
  max_tokens_per_skill: 2000
  max_total_tokens: 5000
  auto_create: true
  require_approval_for_new: true
  disable_threshold: 0.3
  disable_min_uses: 5
  archive_after_days: 90

# --- Memory ---
memory:
  session_db: ~/.kira/sessions.db
  memory_file: ~/.kira/MEMORY.md
  max_entries: 200
  consolidation_interval_hours: 6
  consolidation_model: summarize
  auto_approve: false
  search_results: 5

# --- Tools ---
tools:
  builtin_dir: kira/tools/builtin/
  custom_dir: ~/.kira/tools/
  terminal:
    allowed_commands: ["ls", "cat", "grep", "find", "curl", "git", "python", "pip"]
    blocked_commands: ["rm -rf", "sudo", "shutdown", "reboot"]
    working_directory: ~/
    timeout: 30
  browser:
    enabled: false                     # Enable in Phase 2
    headless: true
  web_search:
    engine: brave                      # brave | searxng | google
    api_key_env: BRAVE_SEARCH_API_KEY

# --- Channels ---
channels:
  cli:
    enabled: true
  api:
    enabled: true
    port: 8080
    auth_token_env: KIRA_API_TOKEN
  telegram:
    enabled: false                     # Enable when ready
    bot_token_env: TELEGRAM_BOT_TOKEN
    allowed_users: []                  # Telegram user IDs
  email:
    enabled: false
    imap_host: imap.gmail.com
    imap_port: 993
    smtp_host: smtp.gmail.com
    smtp_port: 587
    email_env: EMAIL_ADDRESS
    password_env: EMAIL_APP_PASSWORD
    check_interval_seconds: 300

# --- Channel Routing ---
channel_routing:
  urgent: telegram
  reports: email
  approvals: telegram
  default: cli

# --- Scheduler ---
scheduler:
  enabled: true
  heartbeat_file: ~/.kira/HEARTBEAT.md
  check_interval_seconds: 60

# --- Logging ---
logging:
  level: INFO                          # DEBUG | INFO | WARNING | ERROR
  file: ~/.kira/logs/kira.log
  max_size_mb: 50
  rotate_count: 5
  log_tool_calls: true
  log_costs: true

# --- Security ---
security:
  workspace_root: ~/                   # Agent can only access files under this
  approved_domains:                    # URLs the agent can fetch
    - "*.google.com"
    - "*.linkedin.com"
    - "*.github.com"
    - "*.openrouter.ai"
  max_file_size_mb: 10                 # Don't read files larger than this
  sandbox_code_execution: true         # Run code in subprocess with limits
```

### 13.2 secrets.yaml

```yaml
# ~/.kira/secrets.yaml (gitignored, chmod 600)

OPENROUTER_API_KEY: sk-or-...
ANTHROPIC_API_KEY: sk-ant-...
OPENAI_API_KEY: sk-...
TELEGRAM_BOT_TOKEN: "123456:ABC..."
BRAVE_SEARCH_API_KEY: BSA...
EMAIL_ADDRESS: you@gmail.com
EMAIL_APP_PASSWORD: xxxx xxxx xxxx xxxx
KIRA_API_TOKEN: your-random-token
GROQ_API_KEY: gsk_...
GOOGLE_API_KEY: AI...
```

---

## 14. Security Model

### 14.1 Principles

- **Default-deny for destructive actions.** No ALLOW-ALL defaults.
- **No remote code execution without sandboxing.**
- **Workspace isolation.** Agent cannot read files outside `security.workspace_root`.
- **Approval flow for sensitive tools.** Configurable per-tool.
- **Domain allowlist for web requests.** No arbitrary URL fetching.
- **No secrets in conversation history.** Secrets are resolved at runtime, never stored in session DB.

### 14.2 Terminal Sandboxing

```python
class TerminalTool(Tool):
    async def execute(self, arguments: dict, context: ToolContext) -> ToolResult:
        command = arguments["command"]

        # 1. Check against blocked commands
        for blocked in self.config.blocked_commands:
            if blocked in command:
                return ToolResult(success=False, output=f"Blocked command: {blocked}")

        # 2. Check against allowed commands (if allowlist is set)
        if self.config.allowed_commands:
            cmd_name = command.split()[0]
            if cmd_name not in self.config.allowed_commands:
                return ToolResult(success=False, output=f"Command not in allowlist: {cmd_name}")

        # 3. Run in subprocess with timeout and resource limits
        result = await asyncio.create_subprocess_shell(
            command,
            cwd=self.config.working_directory,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(
            result.communicate(),
            timeout=self.config.timeout
        )
        # ... return result
```

---

## 15. Deployment

### 15.1 Minimum Requirements

```
CPU: 1 vCPU (shared is fine)
RAM: 1 GB minimum (256 MB typical RSS)
Disk: 5 GB minimum (10 GB recommended)
OS: Any Linux (Debian/Ubuntu recommended), macOS, or WSL2
Network: Outbound HTTPS only. No inbound ports required unless running API channel.
Python: 3.12+
```

Runs on anything: a $5/month VPS, a Raspberry Pi, a free-tier cloud instance,
a spare laptop, or a container on any orchestrator. No cloud-specific
dependencies. No managed services required.

### 15.2 Process Architecture

```
systemd
  └── kira.service
        ├── Agent Core (main process)
        ├── Scheduler (async task in main process)
        ├── Telegram Listener (async task in main process)
        ├── Email Poller (async task in main process)
        └── API Server (async task in main process)

All async, single process, single event loop.
No Docker required (but supported for sandboxing).
Memory target: <256 MB RSS.
```

### 15.3 File Layout on Disk

```
~/.kira/
  settings.yaml           — Configuration
  secrets.yaml             — API keys (chmod 600)
  SOUL.md                  — Agent identity
  USER.md                  — User profile
  RULES.md                 — Hard constraints
  MEMORY.md                — Long-term knowledge
  HEARTBEAT.md             — Scheduled tasks
  sessions.db              — SQLite session database
  skills/
    store/                 — Active skills
    archive/               — Disabled/old skills
  tools/                   — Custom tool scripts
  logs/
    kira.log               — Application log
```

---

## 16. Development Phases

### Phase 1 — Core Agent (Weeks 1-2)

**Goal**: A working agent you can chat with via CLI that uses any LLM provider.

Deliverables:
- [ ] Provider system: OpenAI-compatible adapter (covers OpenRouter, OpenAI, Groq, Ollama, etc.)
- [ ] Provider system: Anthropic adapter
- [ ] Model router with fallback chain
- [ ] Agent loop: prompt -> LLM -> tool calls -> repeat
- [ ] Context compression
- [ ] Tool registry + built-in tools: terminal, file_read, file_write, file_search, text_search, web_fetch
- [ ] Identity system: SOUL.md, USER.md, RULES.md loading
- [ ] Session DB: SQLite + FTS5
- [ ] CLI REPL with streaming output
- [ ] Basic configuration: settings.yaml + secrets.yaml
- [ ] Logging

### Phase 2 — Skills + Self-Improvement (Weeks 3-4)

**Goal**: The agent learns from successful tasks and gets better over time.

Deliverables:
- [ ] Skill loader: discover, parse, and inject skills
- [ ] Skill relevance matching (keyword + category)
- [ ] Skill evaluator: outcome-based verification
- [ ] Skill lifecycle: create, use, score, improve, prune
- [ ] Agent-created skills with approval flow
- [ ] Memory consolidator (background)
- [ ] MEMORY.md read/write with entry management
- [ ] Web search tool (Brave or SearXNG)
- [ ] REST API channel

### Phase 3 — Channels + Scheduler (Weeks 5-6)

**Goal**: The agent runs 24/7, responds on Telegram, manages email, runs scheduled tasks.

Deliverables:
- [ ] Telegram channel adapter
- [ ] Email channel adapter (IMAP read + SMTP send with approval)
- [ ] Scheduler: HEARTBEAT.md parsing + cron execution
- [ ] Channel routing (urgent -> Telegram, reports -> email)
- [ ] Approval flow via Telegram (inline buttons)
- [ ] Browser tool (Playwright, headless)
- [ ] Deploy to server with systemd (any Linux host)

### Phase 4 — Polish + Advanced (Weeks 7-8)

**Goal**: Production hardening, advanced features.

Deliverables:
- [ ] Google GenAI provider adapter
- [ ] AWS Bedrock provider adapter
- [ ] Skill embedding-based relevance (upgrade from keyword matching)
- [ ] Simple web dashboard (status, costs, recent sessions)
- [ ] Cost tracking and budget alerts
- [ ] Session export/import
- [ ] Discord/Slack adapters (if needed)
- [ ] Code execution sandbox tool
- [ ] PDF reader tool

---

## 17. Tech Stack

| Component | Choice | Why |
|-----------|--------|-----|
| Language | Python 3.12+ | Fastest to build, best LLM ecosystem |
| Async | asyncio + aiohttp | Single process, low memory |
| HTTP client | httpx | Async, streaming, modern |
| Database | SQLite + FTS5 | Zero infrastructure, full-text search built in |
| CLI | prompt_toolkit + rich | Multiline editing, syntax highlighting, streaming |
| Config | PyYAML | Simple, human-readable |
| Schema validation | Pydantic v2 | Fast, type-safe, JSON Schema generation |
| Telegram | python-telegram-bot v21+ | Async, well-maintained |
| Email | aiosmtplib + aioimaplib | Async IMAP/SMTP |
| Browser | playwright | Best automation library |
| Web search | Brave Search API or SearXNG | Brave is cheap; SearXNG is free/self-hosted |
| Tokenizer | tiktoken | Fast, accurate for OpenAI-compat models |
| Testing | pytest + pytest-asyncio | Standard |

**Dependencies kept minimal.** No LangChain, no LlamaIndex, no LiteLLM, no heavyweight frameworks. Direct HTTP calls to provider APIs via httpx.

---

## 18. Key Architectural Decisions

| Pattern | Implementation |
|---------|----------------|
| Skill documents as markdown | YAML frontmatter + markdown body, outcome-based scoring |
| Tool registry (self-registering) | Auto-discovered Python modules with register() function |
| SessionDB (SQLite + FTS5) | Zero-dependency, full-text searchable conversation history |
| Context compression (Head+Summary+Tail) | Cheap model summarizes middle, preserves recent context |
| SOUL.md (agent identity) | Plain markdown personality definition |
| HEARTBEAT.md (scheduled tasks) | Natural language cron definitions |
| Channel plugin pattern | Each platform is a self-contained adapter |
| Memory consolidation | Background process distills sessions into long-term knowledge |
| Self-improving loop | Outcome-verified, never self-judged |
| Provider adapters | Direct httpx calls, no SDK wrappers |

---

## 19. What We Explicitly Do NOT Build

- Mobile apps (use Telegram instead)
- Web-based chat UI (use CLI or Telegram)
- Plugin marketplace or skill hub
- Multi-user support (this is YOUR agent)
- Docker orchestration (single process is enough)
- Telemetry or analytics reporting
- Backward compatibility layers
- Theme/skin engine
- Voice wake-word detection
- RL training infrastructure

---

## 20. Success Criteria

The framework is successful when:

1. You can ask it to apply for a job and it does it correctly (with your approval)
2. You get a useful morning briefing every day at 8 AM without intervention
3. Your email is triaged automatically and drafts are waiting for review
4. Skills created in week 1 are measurably better by week 4
5. You can swap LLM providers in 30 seconds by editing one line in settings.yaml
6. The entire codebase stays under 10,000 lines
7. It runs 24/7 on any server without crashing
8. Monthly LLM cost stays under $30 for normal personal use
