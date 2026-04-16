"""Shared fixtures for all tests."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

from kira.config.loader import build_kira_home, load_config
from kira.core.router import ModelRouter
from kira.memory.sessions import SessionDB
from kira.skills.evaluator import SkillEvaluator
from kira.skills.loader import SkillLoader
from kira.tools.registry import ToolRegistry


@pytest.fixture
def tmp_db():
    """Temporary session database."""
    path = os.path.join(tempfile.mkdtemp(), "test.db")
    db = SessionDB(path)
    yield db
    db.close()


@pytest.fixture
def tool_registry():
    """Tool registry with all built-in tools loaded."""
    reg = ToolRegistry()
    reg.load_builtin()
    return reg


@pytest.fixture
def skill_loader():
    """Skill loader using a fresh copy of skills (so tests don't mutate originals)."""
    import shutil

    src = Path("kira/skills/store")
    tmp_store = Path(tempfile.mkdtemp()) / "store"
    shutil.copytree(src, tmp_store)

    loader = SkillLoader(
        store_dir=str(tmp_store),
        archive_dir=tempfile.mkdtemp(),
    )
    loader.load_all()
    return loader


@pytest.fixture
def skill_evaluator(skill_loader, tmp_db):
    """Skill evaluator wired to loader and test DB."""
    return SkillEvaluator(skill_loader=skill_loader, session_db=tmp_db)


@pytest.fixture
def config():
    """Default config with kira home initialized."""
    build_kira_home()
    return load_config()


@pytest.fixture
def router():
    """Model router with no real providers (for unit tests)."""
    return ModelRouter(
        default="test/model-a",
        fallback_chain=["test/model-b"],
        task_routing={"summarize": "test/model-cheap"},
    )
