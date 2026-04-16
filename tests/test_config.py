"""Tests for configuration loading."""

from __future__ import annotations

import tempfile
from pathlib import Path

import yaml

from kira.config.loader import (
    DEFAULT_SETTINGS,
    _deep_merge,
    _expand_paths,
    build_kira_home,
    load_config,
    resolve_api_key,
)


class TestDeepMerge:
    def test_simple_merge(self):
        base = {"a": 1, "b": 2}
        override = {"b": 3, "c": 4}
        result = _deep_merge(base, override)
        assert result == {"a": 1, "b": 3, "c": 4}

    def test_nested_merge(self):
        base = {"outer": {"a": 1, "b": 2}}
        override = {"outer": {"b": 3, "c": 4}}
        result = _deep_merge(base, override)
        assert result == {"outer": {"a": 1, "b": 3, "c": 4}}

    def test_override_replaces_non_dict(self):
        base = {"key": "old"}
        override = {"key": {"nested": True}}
        result = _deep_merge(base, override)
        assert result == {"key": {"nested": True}}


class TestExpandPaths:
    def test_expands_tilde(self):
        config = {"path": "~/test"}
        expanded = _expand_paths(config)
        assert "~" not in expanded["path"]
        assert expanded["path"].endswith("/test")

    def test_skips_non_paths(self):
        config = {"name": "hello", "count": 5}
        expanded = _expand_paths(config)
        assert expanded["name"] == "hello"


class TestBuildKiraHome:
    def test_creates_directories(self):
        build_kira_home()
        kira_home = Path.home() / ".kira"
        assert kira_home.exists()
        assert (kira_home / "skills" / "store").exists()
        assert (kira_home / "skills" / "archive").exists()
        assert (kira_home / "logs").exists()
        assert (kira_home / "tools").exists()

    def test_creates_default_files(self):
        build_kira_home()
        kira_home = Path.home() / ".kira"
        assert (kira_home / "SOUL.md").exists()
        assert (kira_home / "USER.md").exists()
        assert (kira_home / "RULES.md").exists()
        assert (kira_home / "MEMORY.md").exists()
        assert (kira_home / "HEARTBEAT.md").exists()


class TestLoadConfig:
    def test_loads_defaults(self):
        config = load_config(
            settings_path="/tmp/nonexistent_settings.yaml",
            secrets_path="/tmp/nonexistent_secrets.yaml",
        )
        assert "providers" in config
        assert "routing" in config
        assert "agent" in config
        assert "tools" in config

    def test_merges_user_settings(self):
        tmpdir = Path(tempfile.mkdtemp())
        settings = tmpdir / "settings.yaml"
        settings.write_text(
            yaml.dump(
                {
                    "agent": {"max_iterations": 50},
                    "routing": {"default": "custom/my-model"},
                }
            )
        )

        config = load_config(
            settings_path=str(settings),
            secrets_path=str(tmpdir / "secrets.yaml"),
        )
        assert config["agent"]["max_iterations"] == 50
        assert config["routing"]["default"] == "custom/my-model"
        # Other defaults preserved
        assert config["agent"]["temperature"] == 0.7

    def test_default_settings_complete(self):
        assert "providers" in DEFAULT_SETTINGS
        assert "routing" in DEFAULT_SETTINGS
        assert "agent" in DEFAULT_SETTINGS
        assert "skills" in DEFAULT_SETTINGS
        assert "memory" in DEFAULT_SETTINGS
        assert "tools" in DEFAULT_SETTINGS
        assert "channels" in DEFAULT_SETTINGS
        assert "logging" in DEFAULT_SETTINGS
        assert "security" in DEFAULT_SETTINGS


class TestResolveApiKey:
    def test_from_env(self):
        import os

        os.environ["TEST_API_KEY_XYZ"] = "test-value"
        config = {"providers": {"test": {"api_key_env": "TEST_API_KEY_XYZ"}}}
        key = resolve_api_key(config, "test")
        assert key == "test-value"
        del os.environ["TEST_API_KEY_XYZ"]

    def test_from_config(self):
        config = {"providers": {"test": {"api_key": "direct-key"}}}
        key = resolve_api_key(config, "test")
        assert key == "direct-key"

    def test_missing_provider(self):
        config = {"providers": {}}
        key = resolve_api_key(config, "nonexistent")
        assert key == ""
