"""Tests for identity system and system prompt building."""

from __future__ import annotations

import tempfile
from pathlib import Path

from kira.identity.loader import build_system_prompt, load_file


class TestLoadFile:
    def test_load_existing_file(self):
        path = Path(tempfile.mktemp(suffix=".md"))
        path.write_text("# Test Content")
        assert load_file(str(path)) == "# Test Content"

    def test_load_missing_file(self):
        assert load_file("/tmp/nonexistent_file_xyz.md") == ""


class TestBuildSystemPrompt:
    def test_builds_with_defaults(self, config):
        prompt = build_system_prompt()
        assert len(prompt) > 100
        assert "Kira" in prompt
        assert "Tool Usage" in prompt

    def test_includes_soul(self):
        tmpdir = Path(tempfile.mkdtemp())
        soul = tmpdir / "SOUL.md"
        soul.write_text("You are TestBot, a testing assistant.")

        prompt = build_system_prompt(
            soul_path=str(soul),
            user_path=str(tmpdir / "missing.md"),
            rules_path=str(tmpdir / "missing.md"),
            memory_path=str(tmpdir / "missing.md"),
        )
        assert "TestBot" in prompt

    def test_includes_rules(self):
        tmpdir = Path(tempfile.mkdtemp())
        (tmpdir / "SOUL.md").write_text("# Soul")
        rules = tmpdir / "RULES.md"
        rules.write_text("# Rules\n- Never delete files")

        prompt = build_system_prompt(
            soul_path=str(tmpdir / "SOUL.md"),
            user_path=str(tmpdir / "missing.md"),
            rules_path=str(rules),
            memory_path=str(tmpdir / "missing.md"),
        )
        assert "Never delete files" in prompt

    def test_includes_skills_context(self):
        prompt = build_system_prompt(
            skills_context="### Skill: email-triage\nCheck emails and triage."
        )
        assert "email-triage" in prompt
        assert "Active Skills" in prompt

    def test_excludes_empty_memory(self):
        tmpdir = Path(tempfile.mkdtemp())
        mem = tmpdir / "MEMORY.md"
        mem.write_text("# MEMORY.md — Long-term Knowledge")

        prompt = build_system_prompt(
            soul_path=str(tmpdir / "missing.md"),
            user_path=str(tmpdir / "missing.md"),
            rules_path=str(tmpdir / "missing.md"),
            memory_path=str(mem),
        )
        # Empty memory should not appear
        assert "Relevant Memory" not in prompt

    def test_includes_nonempty_memory(self):
        tmpdir = Path(tempfile.mkdtemp())
        mem = tmpdir / "MEMORY.md"
        mem.write_text("# MEMORY.md\n\n- [2026-04-20] Applied to Stripe")

        prompt = build_system_prompt(
            soul_path=str(tmpdir / "missing.md"),
            user_path=str(tmpdir / "missing.md"),
            rules_path=str(tmpdir / "missing.md"),
            memory_path=str(mem),
        )
        assert "Applied to Stripe" in prompt
