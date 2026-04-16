"""Identity loader — reads SOUL.md, USER.md, RULES.md into system prompt."""

from __future__ import annotations

from pathlib import Path


def load_file(path: str | Path) -> str:
    """Load a markdown identity file, returning empty string if missing."""
    p = Path(path).expanduser()
    if p.exists():
        return p.read_text().strip()
    return ""


def build_system_prompt(
    soul_path: str = "~/.kira/SOUL.md",
    user_path: str = "~/.kira/USER.md",
    rules_path: str = "~/.kira/RULES.md",
    memory_path: str = "~/.kira/MEMORY.md",
    skills_context: str = "",
    extra_context: str = "",
) -> str:
    """Assemble the full system prompt from identity files + context."""
    parts = []

    soul = load_file(soul_path)
    if soul:
        parts.append(soul)

    user = load_file(user_path)
    if user:
        parts.append(f"## User Profile\n\n{user}")

    rules = load_file(rules_path)
    if rules:
        parts.append(rules)

    memory = load_file(memory_path)
    if memory and memory != "# MEMORY.md — Long-term Knowledge":
        # Only include if there's actual content
        lines = memory.strip().split("\n")
        if len(lines) > 1:
            parts.append(f"## Relevant Memory\n\n{memory}")

    if skills_context:
        parts.append(f"## Active Skills\n\n{skills_context}")

    if extra_context:
        parts.append(extra_context)

    # Add tool usage guidance
    parts.append(
        "## Tool Usage\n\n"
        "You have access to tools. Use them to accomplish tasks. "
        "When you need to take an action (read a file, run a command, fetch a URL), "
        "use the appropriate tool rather than describing what you would do. "
        "After tool results come back, analyze them and continue or respond to the user."
    )

    return "\n\n---\n\n".join(parts)
