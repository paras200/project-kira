"""Main entry point — wires everything together.

Modes:
  kira              — CLI REPL + dashboard on port 7777
  kira serve        — Dashboard only (no REPL, for headless servers)
  kira setup google — Google OAuth setup
"""

from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

from kira.config.loader import build_kira_home, load_config, resolve_api_key
from kira.core.agent import Agent
from kira.core.providers import AnthropicAdapter, OpenAICompatibleAdapter
from kira.core.router import ModelRouter
from kira.memory.sessions import SessionDB
from kira.tools.registry import ToolRegistry


def _setup_logging(config: dict):
    log_cfg = config.get("logging", {})
    level = getattr(logging, log_cfg.get("level", "INFO"))
    log_file = log_cfg.get("file")

    handlers: list[logging.Handler] = []
    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.FileHandler(log_path))

    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        handlers=handlers or None,
    )


def _build_router(config: dict) -> ModelRouter:
    routing_cfg = config.get("routing", {})
    router = ModelRouter(
        default=routing_cfg.get("default", "openrouter/anthropic/claude-sonnet-4-20250514"),
        fallback_chain=routing_cfg.get("fallback_chain", []),
        task_routing=routing_cfg.get("task_routing", {}),
    )

    providers_cfg = config.get("providers", {})
    for name, pcfg in providers_cfg.items():
        ptype = pcfg.get("type", "openai_compatible")
        api_key = resolve_api_key(config, name)

        if ptype == "anthropic":
            adapter = AnthropicAdapter(
                api_key=api_key,
                base_url=pcfg.get("base_url", "https://api.anthropic.com"),
            )
        elif ptype in ("openai_compatible", "openai"):
            base_url = pcfg.get("base_url", "https://api.openai.com/v1")
            adapter = OpenAICompatibleAdapter(
                base_url=base_url,
                api_key=api_key,
                default_headers=pcfg.get("default_headers"),
                provider_name=name,
            )
        else:
            logging.warning(f"Unknown provider type: {ptype} for {name}")
            continue

        router.register(name, adapter)
        logging.info(f"Registered provider: {name} ({ptype})")

    return router


def _build_tools(config: dict) -> ToolRegistry:
    registry = ToolRegistry()
    registry.load_builtin()

    custom_dir = config.get("tools", {}).get("custom_dir")
    if custom_dir:
        registry.load_custom(custom_dir)

    return registry


def _handle_subcommand(args: list[str]) -> bool:
    """Handle CLI subcommands. Returns True if handled."""
    if len(args) >= 2 and args[0] == "setup" and args[1] == "google":
        from rich.console import Console

        from kira.integrations.google_auth import (
            CREDENTIALS_PATH,
            is_authenticated,
            is_configured,
            run_auth_flow,
        )

        console = Console()
        build_kira_home()

        if not is_configured():
            console.print(
                "[yellow]Google credentials not found.[/yellow]\n\n"
                "To set up Gmail integration:\n"
                f"  1. Go to https://console.cloud.google.com/\n"
                "  2. Create a project (or use an existing one)\n"
                "  3. Enable the Gmail API (APIs & Services > Enable APIs)\n"
                "  4. Go to Credentials > Create Credentials > OAuth Client ID\n"
                "  5. Choose 'Desktop app' as application type\n"
                "  6. Download the JSON file\n"
                f"  7. Save it as [bold]{CREDENTIALS_PATH}[/bold]\n\n"
                "Then run [bold]kira setup google[/bold] again."
            )
            return True

        if is_authenticated():
            console.print("[green]Already authenticated with Google.[/green]")
            return True

        console.print("Opening browser for Google authorization...")
        try:
            run_auth_flow()
            console.print("[green]Google account connected![/green]")
        except Exception as e:
            console.print(f"[red]Authorization failed: {e}[/red]")
        return True

    return False


def _build_agent(config: dict):
    """Build all components and return the agent."""
    router = _build_router(config)
    tools = _build_tools(config)
    session_db = SessionDB(config.get("memory", {}).get("session_db", "~/.kira/sessions.db"))
    agent = Agent(
        router=router,
        tools=tools,
        session_db=session_db,
        config=config,
    )
    return agent, router, session_db


async def _run_with_dashboard(agent, config, session_db, router, headless=False):
    """Run the dashboard web server and optionally the CLI REPL concurrently."""
    from kira.web.server import DashboardServer

    dashboard_port = config.get("dashboard", {}).get("port", 7777)
    dashboard = DashboardServer(
        session_db=session_db,
        config=config,
        agent=agent,
        port=dashboard_port,
    )

    await dashboard.start()

    if headless:
        # Server-only mode — run until interrupted
        from rich.console import Console

        console = Console()
        console.print(
            f"[bold blue]KIRA[/bold blue] dashboard running at "
            f"[link]http://localhost:{dashboard_port}[/link]\n"
            "Press Ctrl+C to stop."
        )
        try:
            while True:
                await asyncio.sleep(3600)
        except asyncio.CancelledError:
            pass
    else:
        # CLI + dashboard mode
        from rich.console import Console

        console = Console()
        console.print(f"  [dim]Dashboard: http://localhost:{dashboard_port}[/dim]")

        from kira.cli.repl import run_repl

        try:
            await run_repl(agent)
        finally:
            pass

    await dashboard.stop()
    await router.close()
    session_db.close()


def run():
    """Main entry point."""
    # Check for subcommands
    if len(sys.argv) > 1:
        if _handle_subcommand(sys.argv[1:]):
            return

    # Initialize
    build_kira_home()
    config = load_config()
    _setup_logging(config)

    logger = logging.getLogger("kira")
    logger.info("Starting Kira...")

    agent, router, session_db = _build_agent(config)

    headless = len(sys.argv) > 1 and sys.argv[1] == "serve"

    try:
        asyncio.run(_run_with_dashboard(agent, config, session_db, router, headless=headless))
    except KeyboardInterrupt:
        pass
    finally:
        logger.info("Kira stopped.")


if __name__ == "__main__":
    run()
