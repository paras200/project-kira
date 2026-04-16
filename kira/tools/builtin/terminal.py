"""Terminal tool — execute shell commands."""

from __future__ import annotations

import asyncio
import os
from typing import Any

from kira.core.models import ToolContext, ToolResult, ToolSchema
from kira.tools.registry import Tool, ToolRegistry


class TerminalTool(Tool):
    schema = ToolSchema(
        name="terminal",
        description=(
            "Execute a shell command and return its output. "
            "Use this for system operations, running scripts, "
            "installing packages, git commands, etc."
        ),
        parameters={
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "The shell command to execute",
                },
                "working_directory": {
                    "type": "string",
                    "description": "Working directory for the command (optional)",
                },
            },
            "required": ["command"],
        },
        requires_approval=True,
        timeout_seconds=60,
        category="system",
    )

    BLOCKED = ["rm -rf /", "rm -rf ~", "sudo rm", "mkfs", "dd if=", "shutdown", "reboot"]

    async def execute(self, arguments: dict[str, Any], context: ToolContext) -> ToolResult:
        command = arguments["command"]
        cwd = arguments.get("working_directory", context.workspace)
        cwd = os.path.expanduser(cwd)

        # Safety check
        for blocked in self.BLOCKED:
            if blocked in command:
                return ToolResult(
                    success=False,
                    output=f"Blocked command pattern: {blocked}",
                )

        try:
            proc = await asyncio.create_subprocess_shell(
                command,
                cwd=cwd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=self.schema.timeout_seconds
            )
            output_parts = []
            if stdout:
                output_parts.append(stdout.decode(errors="replace"))
            if stderr:
                output_parts.append(f"[stderr] {stderr.decode(errors='replace')}")

            output = "\n".join(output_parts) or "(no output)"
            # Truncate very long output
            if len(output) > 10_000:
                output = output[:5000] + "\n...(truncated)...\n" + output[-2000:]

            return ToolResult(
                success=proc.returncode == 0,
                output=output,
                outcome={"exit_code": proc.returncode},
            )
        except asyncio.TimeoutError:
            return ToolResult(success=False, output=f"Command timed out after {self.schema.timeout_seconds}s")


def register(registry: ToolRegistry):
    registry.register(TerminalTool())
