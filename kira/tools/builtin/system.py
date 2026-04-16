"""System monitoring tools — check health, disk, memory, processes."""

from __future__ import annotations

import platform
import shutil
from typing import Any

from kira.core.models import ToolContext, ToolResult, ToolSchema
from kira.tools.registry import Tool, ToolRegistry


class SystemInfoTool(Tool):
    schema = ToolSchema(
        name="system_info",
        description=(
            "Get system information: OS, CPU, memory, disk usage. "
            "Use this to check server health or available resources."
        ),
        parameters={
            "type": "object",
            "properties": {},
        },
        category="system",
    )

    async def execute(self, arguments: dict[str, Any], context: ToolContext) -> ToolResult:
        import os
        import subprocess

        info = []
        info.append(f"OS: {platform.system()} {platform.release()}")
        info.append(f"Architecture: {platform.machine()}")
        info.append(f"Python: {platform.python_version()}")
        info.append(f"Hostname: {platform.node()}")

        # Disk usage
        for path in ["/", os.path.expanduser("~")]:
            try:
                usage = shutil.disk_usage(path)
                total_gb = usage.total / (1024**3)
                used_gb = usage.used / (1024**3)
                free_gb = usage.free / (1024**3)
                pct = (usage.used / usage.total) * 100
                info.append(
                    f"Disk ({path}): {used_gb:.1f}GB / {total_gb:.1f}GB ({pct:.0f}% used, {free_gb:.1f}GB free)"
                )
            except Exception:
                pass

        # Memory (cross-platform)
        try:
            if platform.system() == "Darwin":
                result = subprocess.run(
                    ["sysctl", "-n", "hw.memsize"], capture_output=True, text=True, timeout=5
                )
                if result.returncode == 0:
                    total_bytes = int(result.stdout.strip())
                    info.append(f"RAM: {total_bytes / (1024**3):.1f}GB total")
            elif platform.system() == "Linux":
                with open("/proc/meminfo") as f:
                    meminfo = f.read()
                for line in meminfo.splitlines():
                    if line.startswith(("MemTotal", "MemAvailable")):
                        key, val = line.split(":")
                        kb = int(val.strip().split()[0])
                        info.append(f"{key.strip()}: {kb / (1024**2):.1f}GB")
        except Exception:
            pass

        # Load average
        try:
            load = os.getloadavg()
            info.append(f"Load average: {load[0]:.2f} {load[1]:.2f} {load[2]:.2f}")
        except Exception:
            pass

        # Uptime
        try:
            if platform.system() == "Linux":
                with open("/proc/uptime") as f:
                    uptime_secs = float(f.read().split()[0])
                hours = int(uptime_secs // 3600)
                days = hours // 24
                info.append(f"Uptime: {days}d {hours % 24}h")
            elif platform.system() == "Darwin":
                result = subprocess.run(["uptime"], capture_output=True, text=True, timeout=5)
                if result.returncode == 0:
                    info.append(f"Uptime: {result.stdout.strip()}")
        except Exception:
            pass

        return ToolResult(
            success=True,
            output="\n".join(info),
            outcome={"system_checked": True},
        )


def register(registry: ToolRegistry):
    registry.register(SystemInfoTool())
