"""Configuration loader. Reads settings.yaml + secrets.yaml."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml


DEFAULT_SETTINGS: dict[str, Any] = {
    "providers": {},
    "routing": {
        "default": "openrouter/anthropic/claude-sonnet-4-20250514",
        "fallback_chain": [],
        "task_routing": {},
    },
    "agent": {
        "max_iterations": 25,
        "max_input_tokens": 100_000,
        "max_output_tokens": 16_000,
        "max_cost_per_turn": 1.00,
        "temperature": 0.7,
        "compression_threshold": 0.6,
    },
    "skills": {
        "store": "~/.kira/skills/",
        "archive": "~/.kira/skills/archive/",
        "max_per_turn": 3,
        "max_tokens_per_skill": 2000,
        "auto_create": True,
        "require_approval_for_new": True,
        "disable_threshold": 0.3,
        "disable_min_uses": 5,
    },
    "memory": {
        "session_db": "~/.kira/sessions.db",
        "memory_file": "~/.kira/MEMORY.md",
        "max_entries": 200,
        "consolidation_interval_hours": 6,
        "auto_approve": False,
        "search_results": 5,
    },
    "tools": {
        "custom_dir": "~/.kira/tools/",
        "terminal": {
            "allowed_commands": [],
            "blocked_commands": ["rm -rf", "sudo", "shutdown", "reboot"],
            "working_directory": "~/",
            "timeout": 30,
        },
        "web_search": {
            "engine": "brave",
            "api_key_env": "BRAVE_SEARCH_API_KEY",
        },
    },
    "channels": {
        "cli": {"enabled": True},
        "api": {"enabled": False, "port": 8080},
        "telegram": {"enabled": False},
        "email": {"enabled": False},
    },
    "scheduler": {
        "enabled": True,
        "heartbeat_file": "~/.kira/HEARTBEAT.md",
        "check_interval_seconds": 60,
    },
    "logging": {
        "level": "INFO",
        "file": "~/.kira/logs/kira.log",
        "log_tool_calls": True,
        "log_costs": True,
    },
    "security": {
        "workspace_root": "~/",
        "max_file_size_mb": 10,
        "sandbox_code_execution": True,
    },
}


def _deep_merge(base: dict, override: dict) -> dict:
    """Recursively merge override into base."""
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def _resolve_env_vars(secrets: dict[str, str]) -> dict[str, str]:
    """Put secrets into os.environ so they're accessible everywhere."""
    for key, value in secrets.items():
        if isinstance(value, str):
            os.environ.setdefault(key, value)
    return secrets


def _expand_paths(config: dict) -> dict:
    """Expand ~ in path values."""
    for key, value in config.items():
        if isinstance(value, str) and "~" in value:
            config[key] = str(Path(value).expanduser())
        elif isinstance(value, dict):
            config[key] = _expand_paths(value)
    return config


def load_config(
    settings_path: str | Path | None = None,
    secrets_path: str | Path | None = None,
) -> dict[str, Any]:
    """Load and merge settings.yaml + secrets.yaml + defaults."""
    kira_home = Path.home() / ".kira"

    if settings_path is None:
        settings_path = kira_home / "settings.yaml"
    if secrets_path is None:
        secrets_path = kira_home / "secrets.yaml"

    settings_path = Path(settings_path)
    secrets_path = Path(secrets_path)

    # Start with defaults
    config = DEFAULT_SETTINGS.copy()

    # Merge settings.yaml if it exists
    if settings_path.exists():
        with open(settings_path) as f:
            user_settings = yaml.safe_load(f) or {}
        config = _deep_merge(config, user_settings)

    # Load secrets
    if secrets_path.exists():
        with open(secrets_path) as f:
            secrets = yaml.safe_load(f) or {}
        _resolve_env_vars(secrets)

    # Expand ~ in all path values
    config = _expand_paths(config)

    return config


def resolve_api_key(config: dict, provider_name: str) -> str:
    """Get the API key for a provider from env var or config."""
    provider_cfg = config.get("providers", {}).get(provider_name, {})
    api_key_env = provider_cfg.get("api_key_env", "")
    api_key = provider_cfg.get("api_key", "")

    if api_key_env:
        return os.environ.get(api_key_env, api_key)
    return api_key


def build_kira_home():
    """Create ~/.kira directory structure if it doesn't exist."""
    kira_home = Path.home() / ".kira"
    dirs = [
        kira_home,
        kira_home / "skills" / "store",
        kira_home / "skills" / "archive",
        kira_home / "tools",
        kira_home / "logs",
    ]
    for d in dirs:
        d.mkdir(parents=True, exist_ok=True)

    # Create default files if they don't exist
    defaults = {
        kira_home / "SOUL.md": _default_soul(),
        kira_home / "USER.md": _default_user(),
        kira_home / "RULES.md": _default_rules(),
        kira_home / "MEMORY.md": "# MEMORY.md — Long-term Knowledge\n",
        kira_home / "HEARTBEAT.md": "# HEARTBEAT.md — Recurring Tasks\n",
    }
    for path, content in defaults.items():
        if not path.exists():
            path.write_text(content)


def _default_soul() -> str:
    return """# SOUL.md

You are Kira, a personal AI assistant.

## Personality
- Direct and concise. No fluff.
- Proactive — suggest improvements when you see them.
- Honest about limitations. Say "I don't know" rather than guessing.

## Communication Style
- Default to short responses unless asked for detail.
- Use bullet points over paragraphs.

## Core Behaviors
- Always confirm before taking irreversible actions.
- When a task is ambiguous, ask ONE clarifying question.
- Prefer doing over discussing.
"""


def _default_user() -> str:
    return """# USER.md

## Profile
- Name: (not set)
- Timezone: (not set)

## Preferences
- (Add your preferences here)
"""


def _default_rules() -> str:
    return """# RULES.md — Hard Constraints

## Never Do
- Never send an email without explicit approval
- Never delete files without confirmation
- Never share personal information with external services
- Never execute commands with `rm -rf` or destructive equivalents

## Always Do
- Always log tool executions with timestamps
- Always save drafts before sending any communication
- Always cite sources in research summaries

## Security
- Never include API keys or passwords in responses
- Never execute code from untrusted sources without sandboxing
"""
