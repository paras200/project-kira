"""Tests for web dashboard server and API endpoints."""

from __future__ import annotations

import aiohttp
import pytest

from kira.cli.main import _build_agent
from kira.config.loader import build_kira_home, load_config
from kira.web.server import DashboardServer


@pytest.fixture
async def dashboard():
    """Start a dashboard server for testing, tear down after."""
    build_kira_home()
    config = load_config()
    agent, router, sdb = _build_agent(config)

    server = DashboardServer(session_db=sdb, config=config, agent=agent, port=7799)
    await server.start()
    yield server
    await server.stop()
    sdb.close()


class TestDashboardAPI:
    @pytest.mark.asyncio
    async def test_health_endpoint(self, dashboard):
        async with aiohttp.ClientSession() as session:
            async with session.get("http://localhost:7799/api/health") as resp:
                assert resp.status == 200
                data = await resp.json()
                assert data["status"] == "running"
                assert data["tools_count"] >= 22
                assert data["skills_count"] >= 1
                assert "uptime" in data
                assert "providers" in data

    @pytest.mark.asyncio
    async def test_providers_endpoint(self, dashboard):
        async with aiohttp.ClientSession() as session:
            async with session.get("http://localhost:7799/api/providers") as resp:
                assert resp.status == 200
                data = await resp.json()
                assert "providers" in data
                assert "routing" in data
                assert "default" in data["routing"]

    @pytest.mark.asyncio
    async def test_sessions_endpoint(self, dashboard):
        async with aiohttp.ClientSession() as session:
            async with session.get("http://localhost:7799/api/sessions") as resp:
                assert resp.status == 200
                data = await resp.json()
                assert "sessions" in data

    @pytest.mark.asyncio
    async def test_skills_endpoint(self, dashboard):
        async with aiohttp.ClientSession() as session:
            async with session.get("http://localhost:7799/api/skills") as resp:
                assert resp.status == 200
                data = await resp.json()
                assert "skills" in data
                assert len(data["skills"]) >= 7
                assert "recent_evaluations" in data

    @pytest.mark.asyncio
    async def test_integrations_endpoint(self, dashboard):
        async with aiohttp.ClientSession() as session:
            async with session.get("http://localhost:7799/api/integrations") as resp:
                assert resp.status == 200
                data = await resp.json()
                assert "gmail" in data
                assert "telegram" in data
                assert "configured" in data["gmail"]

    @pytest.mark.asyncio
    async def test_activity_endpoint(self, dashboard):
        async with aiohttp.ClientSession() as session:
            async with session.get("http://localhost:7799/api/activity") as resp:
                assert resp.status == 200
                data = await resp.json()
                assert "activity" in data

    @pytest.mark.asyncio
    async def test_identity_endpoint(self, dashboard):
        async with aiohttp.ClientSession() as session:
            async with session.get("http://localhost:7799/api/identity") as resp:
                assert resp.status == 200
                data = await resp.json()
                assert "SOUL.md" in data
                assert "USER.md" in data
                assert "RULES.md" in data
                assert "MEMORY.md" in data
                assert "HEARTBEAT.md" in data

    @pytest.mark.asyncio
    async def test_identity_save(self, dashboard):
        async with aiohttp.ClientSession() as session:
            # Save
            async with session.post(
                "http://localhost:7799/api/identity",
                json={"filename": "USER.md", "content": "# Test User\nName: Test"},
            ) as resp:
                assert resp.status == 200
                data = await resp.json()
                assert data["status"] == "saved"

            # Verify
            async with session.get("http://localhost:7799/api/identity") as resp:
                data = await resp.json()
                assert "Test User" in data["USER.md"]

    @pytest.mark.asyncio
    async def test_identity_save_invalid_file(self, dashboard):
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "http://localhost:7799/api/identity",
                json={"filename": "EVIL.md", "content": "bad"},
            ) as resp:
                assert resp.status == 400

    @pytest.mark.asyncio
    async def test_dashboard_html(self, dashboard):
        async with aiohttp.ClientSession() as session:
            async with session.get("http://localhost:7799/") as resp:
                assert resp.status == 200
                html = await resp.text()
                assert "Kira Dashboard" in html
                assert "Overview" in html
                assert "Skills" in html

    @pytest.mark.asyncio
    async def test_config_endpoint(self, dashboard):
        async with aiohttp.ClientSession() as session:
            async with session.get("http://localhost:7799/api/config") as resp:
                assert resp.status == 200
                data = await resp.json()
                assert "routing" in data
                assert "agent" in data

    @pytest.mark.asyncio
    async def test_session_detail_not_found(self, dashboard):
        async with aiohttp.ClientSession() as session:
            async with session.get("http://localhost:7799/api/sessions/nonexistent") as resp:
                assert resp.status == 404
