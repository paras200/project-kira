"""Kira web dashboard — configuration, monitoring, and activity feed."""

from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import yaml
from aiohttp import web

from kira.config.loader import load_config
from kira.integrations.google_auth import is_authenticated, is_configured
from kira.memory.sessions import SessionDB

logger = logging.getLogger(__name__)

KIRA_HOME = Path.home() / ".kira"
STATIC_DIR = Path(__file__).parent / "static"


class DashboardServer:
    """Web dashboard for Kira — config, monitoring, activity."""

    def __init__(
        self,
        session_db: SessionDB,
        config: dict[str, Any],
        agent: Any = None,
        host: str = "0.0.0.0",
        port: int = 7777,
    ):
        self.session_db = session_db
        self.config = config
        self.agent = agent
        self.host = host
        self.port = port
        self._start_time = time.time()
        self._app: Optional[web.Application] = None
        self._runner: Optional[web.AppRunner] = None

    def _build_app(self) -> web.Application:
        app = web.Application()
        app.router.add_get("/", self._serve_dashboard)
        app.router.add_get("/api/health", self._api_health)
        app.router.add_get("/api/config", self._api_config)
        app.router.add_post("/api/config", self._api_save_config)
        app.router.add_get("/api/providers", self._api_providers)
        app.router.add_get("/api/sessions", self._api_sessions)
        app.router.add_get("/api/sessions/{session_id}", self._api_session_detail)
        app.router.add_get("/api/skills", self._api_skills)
        app.router.add_get("/api/integrations", self._api_integrations)
        app.router.add_get("/api/activity", self._api_activity)
        app.router.add_get("/api/identity", self._api_identity)
        app.router.add_post("/api/identity", self._api_save_identity)
        return app

    async def start(self):
        self._app = self._build_app()
        self._runner = web.AppRunner(self._app)
        await self._runner.setup()
        site = web.TCPSite(self._runner, self.host, self.port)
        await site.start()
        logger.info(f"Dashboard running at http://{self.host}:{self.port}")

    async def stop(self):
        if self._runner:
            await self._runner.cleanup()

    # --- Dashboard HTML ---

    async def _serve_dashboard(self, request: web.Request) -> web.Response:
        html_path = Path(__file__).parent / "dashboard.html"
        if html_path.exists():
            return web.Response(
                text=html_path.read_text(), content_type="text/html"
            )
        return web.Response(text="Dashboard not found", status=404)

    # --- API Endpoints ---

    async def _api_health(self, request: web.Request) -> web.Response:
        uptime = int(time.time() - self._start_time)
        hours, remainder = divmod(uptime, 3600)
        minutes, seconds = divmod(remainder, 60)

        # Count active components
        providers = list(self.config.get("providers", {}).keys())
        tools = []
        if self.agent:
            tools = [s.name for s in self.agent.tools.list_schemas()]

        skills_count = 0
        if self.agent and hasattr(self.agent, "skill_loader"):
            skills_count = len(self.agent.skill_loader.all_skills)

        sessions = self.session_db.list_sessions(limit=1)
        total_sessions = len(self.session_db.list_sessions(limit=1000))

        return web.json_response(
            {
                "status": "running",
                "uptime": f"{hours}h {minutes}m {seconds}s",
                "uptime_seconds": uptime,
                "providers": providers,
                "providers_count": len(providers),
                "tools": tools,
                "tools_count": len(tools),
                "skills_count": skills_count,
                "sessions_count": total_sessions,
                "default_model": self.config.get("routing", {}).get("default", "not set"),
                "gmail_connected": is_authenticated() if is_configured() else False,
                "gmail_configured": is_configured(),
            }
        )

    async def _api_config(self, request: web.Request) -> web.Response:
        # Return config with secrets masked
        safe_config = json.loads(json.dumps(self.config, default=str))
        # Mask API keys
        for pname, pcfg in safe_config.get("providers", {}).items():
            if "api_key" in pcfg and pcfg["api_key"]:
                pcfg["api_key"] = "***masked***"
            if "api_key_env" in pcfg:
                env_val = os.environ.get(pcfg["api_key_env"], "")
                pcfg["api_key_status"] = "set" if env_val else "not set"
        return web.json_response(safe_config)

    async def _api_save_config(self, request: web.Request) -> web.Response:
        try:
            data = await request.json()
            section = data.get("section")
            values = data.get("values")

            if not section or not values:
                return web.json_response(
                    {"error": "section and values required"}, status=400
                )

            # Load current settings
            settings_path = KIRA_HOME / "settings.yaml"
            current = {}
            if settings_path.exists():
                with open(settings_path) as f:
                    current = yaml.safe_load(f) or {}

            # Update section
            current[section] = values

            # Write back
            with open(settings_path, "w") as f:
                yaml.dump(current, f, default_flow_style=False, sort_keys=False)

            # Reload config
            self.config = load_config()

            return web.json_response({"status": "saved", "section": section})
        except Exception as e:
            return web.json_response({"error": str(e)}, status=500)

    async def _api_providers(self, request: web.Request) -> web.Response:
        providers = []
        for name, pcfg in self.config.get("providers", {}).items():
            api_key_env = pcfg.get("api_key_env", "")
            has_key = bool(os.environ.get(api_key_env, pcfg.get("api_key", "")))
            registered = (
                self.agent and name in self.agent.router.providers
            )
            providers.append(
                {
                    "name": name,
                    "type": pcfg.get("type", "openai_compatible"),
                    "base_url": pcfg.get("base_url", ""),
                    "models": pcfg.get("models", []),
                    "api_key_configured": has_key,
                    "registered": bool(registered),
                }
            )

        routing = self.config.get("routing", {})
        return web.json_response(
            {
                "providers": providers,
                "routing": {
                    "default": routing.get("default", ""),
                    "fallback_chain": routing.get("fallback_chain", []),
                    "task_routing": routing.get("task_routing", {}),
                },
            }
        )

    async def _api_sessions(self, request: web.Request) -> web.Response:
        limit = int(request.query.get("limit", "20"))
        sessions = self.session_db.list_sessions(limit=limit)
        return web.json_response({"sessions": sessions})

    async def _api_session_detail(self, request: web.Request) -> web.Response:
        session_id = request.match_info["session_id"]
        session = self.session_db.get_session(session_id)
        if not session:
            return web.json_response({"error": "not found"}, status=404)
        messages = self.session_db.get_messages(session_id)
        return web.json_response(
            {"session": session, "messages": messages}
        )

    async def _api_skills(self, request: web.Request) -> web.Response:
        skills = []
        if self.agent and hasattr(self.agent, "skill_evaluator"):
            skills = self.agent.skill_evaluator.get_skill_stats()

            # Also get recent evaluations
            evals = self.session_db._conn.execute(
                "SELECT * FROM skill_evaluations ORDER BY created_at DESC LIMIT 20"
            ).fetchall()
            recent_evals = [dict(e) for e in evals]
        else:
            recent_evals = []

        return web.json_response(
            {"skills": skills, "recent_evaluations": recent_evals}
        )

    async def _api_integrations(self, request: web.Request) -> web.Response:
        integrations = {
            "gmail": {
                "configured": is_configured(),
                "authenticated": is_authenticated() if is_configured() else False,
                "credentials_path": str(KIRA_HOME / "google_credentials.json"),
                "setup_command": "kira setup google",
            },
            "telegram": {
                "configured": self.config.get("channels", {})
                .get("telegram", {})
                .get("enabled", False),
                "status": "not implemented yet",
            },
        }

        # Get Gmail profile if authenticated
        if integrations["gmail"]["authenticated"]:
            try:
                from kira.tools.builtin.gmail import _get_gmail_service

                service = _get_gmail_service()
                if service:
                    profile = (
                        service.users().getProfile(userId="me").execute()
                    )
                    integrations["gmail"]["email"] = profile.get("emailAddress")
                    integrations["gmail"]["total_messages"] = profile.get("messagesTotal")
            except Exception:
                pass

        return web.json_response(integrations)

    async def _api_activity(self, request: web.Request) -> web.Response:
        """Recent activity feed — last N sessions with tool usage summary."""
        limit = int(request.query.get("limit", "10"))
        sessions = self.session_db.list_sessions(limit=limit)

        activity = []
        for s in sessions:
            messages = self.session_db.get_messages(s["id"])
            tools_used = []
            for m in messages:
                if m["role"] == "tool" and m.get("tool_name"):
                    tools_used.append(m["tool_name"])

            user_msgs = [m for m in messages if m["role"] == "user"]
            first_msg = user_msgs[0]["content"][:120] if user_msgs else ""

            activity.append(
                {
                    "session_id": s["id"],
                    "title": s.get("title") or first_msg or "(empty session)",
                    "channel": s.get("channel", "cli"),
                    "created_at": s.get("created_at"),
                    "updated_at": s.get("updated_at"),
                    "message_count": s.get("message_count", 0),
                    "total_tokens": s.get("total_tokens", 0),
                    "total_cost": s.get("total_cost_usd", 0.0),
                    "tools_used": tools_used,
                    "preview": first_msg,
                }
            )

        return web.json_response({"activity": activity})

    async def _api_identity(self, request: web.Request) -> web.Response:
        """Get identity files content."""
        identity = {}
        for name in ("SOUL.md", "USER.md", "RULES.md", "MEMORY.md", "HEARTBEAT.md"):
            path = KIRA_HOME / name
            identity[name] = path.read_text() if path.exists() else ""
        return web.json_response(identity)

    async def _api_save_identity(self, request: web.Request) -> web.Response:
        """Save identity file content."""
        try:
            data = await request.json()
            filename = data.get("filename")
            content = data.get("content")

            allowed = {"SOUL.md", "USER.md", "RULES.md", "MEMORY.md", "HEARTBEAT.md"}
            if filename not in allowed:
                return web.json_response(
                    {"error": f"Invalid file: {filename}"}, status=400
                )

            path = KIRA_HOME / filename
            path.write_text(content)
            return web.json_response({"status": "saved", "filename": filename})
        except Exception as e:
            return web.json_response({"error": str(e)}, status=500)
