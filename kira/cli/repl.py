"""Interactive REPL for Kira."""

from __future__ import annotations

import asyncio
import sys
from typing import Any

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.text import Text

from kira.core.agent import Agent
from kira.core.models import ToolResult
from kira.integrations.google_auth import (
    CREDENTIALS_PATH,
    is_authenticated,
    is_configured,
    run_auth_flow,
)

console = Console()


def _setup_google():
    """Run Google OAuth2 setup flow."""
    if not is_configured():
        console.print(
            "[yellow]Google credentials not found.[/yellow]\n\n"
            "To set up Gmail integration:\n"
            f"  1. Go to [link]https://console.cloud.google.com/[/link]\n"
            "  2. Create a project (or use an existing one)\n"
            "  3. Enable the Gmail API (APIs & Services > Enable APIs)\n"
            "  4. Go to Credentials > Create Credentials > OAuth Client ID\n"
            "  5. Choose 'Desktop app' as application type\n"
            "  6. Download the JSON file\n"
            f"  7. Save it as [bold]{CREDENTIALS_PATH}[/bold]\n\n"
            "Then run [bold]/setup google[/bold] again."
        )
        return

    if is_authenticated():
        console.print("[green]Already authenticated with Google.[/green]")
        return

    console.print("Opening browser for Google authorization...")
    try:
        run_auth_flow()
        console.print("[green]Google account connected successfully![/green]")
        console.print(
            "You can now use Gmail tools: gmail_search, gmail_read, "
            "gmail_send, gmail_draft, gmail_label"
        )
    except Exception as e:
        console.print(f"[red]Authorization failed: {e}[/red]")


def _gmail_status():
    """Check Gmail connection status."""
    if not is_configured():
        console.print("[red]Not configured.[/red] Run /setup google")
        return

    if not is_authenticated():
        console.print("[yellow]Credentials found but not authenticated.[/yellow] Run /setup google")
        return

    console.print("[green]Gmail connected.[/green]")
    try:
        from kira.tools.builtin.gmail import _get_gmail_service

        service = _get_gmail_service()
        if service:
            profile = service.users().getProfile(userId="me").execute()
            console.print(f"  Email: {profile.get('emailAddress', '?')}")
            console.print(f"  Total messages: {profile.get('messagesTotal', '?')}")
            console.print(f"  Threads: {profile.get('threadsTotal', '?')}")
    except Exception as e:
        console.print(f"[red]Error checking status: {e}[/red]")


def _print_token(token: str):
    """Print a streaming token without newline."""
    sys.stdout.write(token)
    sys.stdout.flush()


def _on_tool_start(name: str, args: dict[str, Any]):
    """Display when a tool starts executing."""
    args_short = str(args)
    if len(args_short) > 100:
        args_short = args_short[:100] + "..."
    console.print(f"\n  [dim]> {name}({args_short})[/dim]")


def _on_tool_end(name: str, result: ToolResult):
    """Display when a tool finishes."""
    status = "[green]OK[/green]" if result.success else "[red]FAIL[/red]"
    output_preview = result.output[:200].replace("\n", " ")
    if len(result.output) > 200:
        output_preview += "..."
    console.print(f"  [dim]  {status} {output_preview}[/dim]")


def _on_skill_event(event: str, data: dict):
    """Display skill system events."""
    if event == "evaluated":
        status = "[green]PASS[/green]" if data["success"] else "[red]FAIL[/red]"
        console.print(
            f"\n  [dim]skill[/dim] {data['skill']} {status} "
            f"[dim](rate: {data['success_rate']:.0%}, uses: {data['use_count']})[/dim]"
        )
    elif event == "eligible_for_creation":
        console.print(
            f"\n  [dim]skill[/dim] [cyan]New skill candidate detected[/cyan] "
            f"[dim](tools: {', '.join(data['tools_used'])})[/dim]"
        )


async def run_repl(agent: Agent):
    """Main REPL loop."""
    console.print(
        Panel(
            "[bold]KIRA[/bold] — Knowledge-driven Intelligent Reasoning Agent\n"
            "Type your message. Press Enter to send. Ctrl+C or 'exit' to quit.",
            style="blue",
        )
    )

    session_id = agent.session_db.create_session(channel="cli")

    while True:
        try:
            console.print()
            user_input = console.input("[bold green]you>[/bold green] ")
        except (KeyboardInterrupt, EOFError):
            console.print("\n[dim]Goodbye.[/dim]")
            break

        user_input = user_input.strip()
        if not user_input:
            continue
        if user_input.lower() in ("exit", "quit", "/quit", "/exit"):
            console.print("[dim]Goodbye.[/dim]")
            break

        if user_input == "/new":
            session_id = agent.session_db.create_session(channel="cli")
            console.print("[dim]New session started.[/dim]")
            continue

        if user_input == "/sessions":
            sessions = agent.session_db.list_sessions()
            for s in sessions:
                title = s.get("title") or "(untitled)"
                console.print(
                    f"  [dim]{s['id']}[/dim] {title} "
                    f"[dim]({s['message_count']} msgs, "
                    f"${s['total_cost_usd']:.4f})[/dim]"
                )
            continue

        if user_input.startswith("/search "):
            query = user_input[8:]
            results = agent.session_db.search(query)
            if not results:
                console.print("[dim]No results.[/dim]")
            for r in results:
                console.print(
                    f"  [dim]{r.get('session_title', '?')}[/dim]: "
                    f"{r['content'][:100]}"
                )
            continue

        if user_input == "/cost":
            session = agent.session_db.get_session(session_id)
            if session:
                console.print(
                    f"  Tokens: {session['total_tokens']} | "
                    f"Cost: ${session['total_cost_usd']:.4f} | "
                    f"Messages: {session['message_count']}"
                )
            continue

        if user_input == "/setup google":
            _setup_google()
            continue

        if user_input == "/gmail status":
            _gmail_status()
            continue

        if user_input == "/skills":
            stats = agent.skill_evaluator.get_skill_stats()
            if not stats:
                console.print("[dim]No skills yet. Skills are created as you use Kira.[/dim]")
            else:
                console.print(f"  [bold]Skills ({len(stats)} total)[/bold]")
                for s in stats:
                    rate = f"{s['success_rate']:.0%}"
                    badge = "[green]" if s["success_rate"] >= 0.7 else "[yellow]" if s["success_rate"] >= 0.3 else "[red]"
                    console.print(
                        f"  {badge}{s['name']}[/] "
                        f"— {rate} success ({s['use_count']} uses) "
                        f"v{s['version']} [{s['created_by']}]"
                    )
            continue

        if user_input.startswith("/skills reload"):
            agent.skill_loader.load_all()
            console.print(f"[dim]Reloaded {len(agent.skill_loader.all_skills)} skills.[/dim]")
            continue

        if user_input == "/help":
            console.print(
                "  /new            — Start a new session\n"
                "  /sessions       — List recent sessions\n"
                "  /search <q>     — Search past conversations\n"
                "  /cost           — Show session cost\n"
                "  /skills         — List all skills and their stats\n"
                "  /skills reload  — Reload skills from disk\n"
                "  /setup google   — Connect your Google account (Gmail)\n"
                "  /gmail status   — Check Gmail connection status\n"
                "  /help           — Show this help\n"
                "  exit            — Quit"
            )
            continue

        # Run the agent
        console.print()
        console.print("[bold blue]kira>[/bold blue] ", end="")

        try:
            response = await agent.run_turn(
                user_message=user_input,
                session_id=session_id,
                on_token=_print_token,
                on_tool_start=_on_tool_start,
                on_tool_end=_on_tool_end,
                on_skill_event=_on_skill_event,
            )
            # If we were streaming, the text is already printed.
            # If not streaming (fallback), print the response.
            if not response:
                console.print("[dim](no response)[/dim]")
            else:
                # Add a newline after streaming output
                sys.stdout.write("\n")
                sys.stdout.flush()

        except KeyboardInterrupt:
            console.print("\n[dim]Interrupted.[/dim]")
        except Exception as e:
            console.print(f"\n[red]Error: {e}[/red]")
