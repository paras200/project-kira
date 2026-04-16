"""Tool registry — self-registering tool catalog with dispatch."""

from __future__ import annotations

import asyncio
import importlib
import logging
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from kira.core.models import ToolContext, ToolResult, ToolSchema

logger = logging.getLogger(__name__)


class Tool(ABC):
    """Base class for all tools."""

    schema: ToolSchema

    @abstractmethod
    async def execute(self, arguments: dict[str, Any], context: ToolContext) -> ToolResult:
        ...

    def validate(self, arguments: dict[str, Any]) -> bool:
        """Basic validation: check required fields exist."""
        required = self.schema.parameters.get("required", [])
        props = self.schema.parameters.get("properties", {})
        for field in required:
            if field not in arguments:
                return False
        return True


class ToolRegistry:
    """Discovers, registers, and dispatches tools."""

    def __init__(self):
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool):
        self._tools[tool.schema.name] = tool
        logger.debug(f"Registered tool: {tool.schema.name}")

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    @property
    def tools(self) -> dict[str, Tool]:
        return self._tools

    def list_schemas(self, categories: list[str] | None = None) -> list[ToolSchema]:
        schemas = []
        for tool in self._tools.values():
            if categories and tool.schema.category not in categories:
                continue
            schemas.append(tool.schema)
        return schemas

    async def execute(
        self, name: str, arguments: dict[str, Any], context: ToolContext
    ) -> ToolResult:
        tool = self.get(name)
        if tool is None:
            return ToolResult(success=False, output=f"Unknown tool: {name}")
        if not tool.validate(arguments):
            return ToolResult(
                success=False,
                output=f"Invalid arguments for {name}. Required: "
                f"{tool.schema.parameters.get('required', [])}",
            )
        try:
            return await asyncio.wait_for(
                tool.execute(arguments, context),
                timeout=tool.schema.timeout_seconds,
            )
        except asyncio.TimeoutError:
            return ToolResult(
                success=False,
                output=f"Tool {name} timed out after {tool.schema.timeout_seconds}s",
            )
        except Exception as e:
            logger.error(f"Tool {name} failed: {e}", exc_info=True)
            return ToolResult(success=False, output=f"Tool {name} error: {e}")

    def load_builtin(self):
        """Import all built-in tools from kira.tools.builtin."""
        builtin_dir = Path(__file__).parent / "builtin"
        for py_file in sorted(builtin_dir.glob("*.py")):
            if py_file.name.startswith("_"):
                continue
            module_name = f"kira.tools.builtin.{py_file.stem}"
            try:
                mod = importlib.import_module(module_name)
                # Each module should have a `register` function
                if hasattr(mod, "register"):
                    mod.register(self)
                    logger.debug(f"Loaded built-in tools from {py_file.name}")
            except Exception as e:
                logger.warning(f"Failed to load {module_name}: {e}")

    def load_custom(self, custom_dir: str | Path):
        """Import custom tools from a directory."""
        custom_path = Path(custom_dir)
        if not custom_path.exists():
            return
        import sys

        if str(custom_path.parent) not in sys.path:
            sys.path.insert(0, str(custom_path.parent))

        for py_file in sorted(custom_path.glob("*.py")):
            if py_file.name.startswith("_"):
                continue
            module_name = py_file.stem
            try:
                mod = importlib.import_module(module_name)
                if hasattr(mod, "register"):
                    mod.register(self)
                    logger.debug(f"Loaded custom tool from {py_file.name}")
            except Exception as e:
                logger.warning(f"Failed to load custom tool {py_file.name}: {e}")
