"""File tools — read, write, search files."""

from __future__ import annotations

import fnmatch
import os
from pathlib import Path
from typing import Any

from kira.core.models import ToolContext, ToolResult, ToolSchema
from kira.tools.registry import Tool, ToolRegistry


class FileReadTool(Tool):
    schema = ToolSchema(
        name="file_read",
        description="Read the contents of a file. Returns the text content.",
        parameters={
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Path to the file to read",
                },
                "offset": {
                    "type": "integer",
                    "description": "Line number to start reading from (0-based)",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of lines to read",
                },
            },
            "required": ["path"],
        },
        category="filesystem",
    )

    async def execute(self, arguments: dict[str, Any], context: ToolContext) -> ToolResult:
        path = Path(arguments["path"]).expanduser().resolve()

        if not path.exists():
            return ToolResult(success=False, output=f"File not found: {path}")
        if not path.is_file():
            return ToolResult(success=False, output=f"Not a file: {path}")
        if path.stat().st_size > 10 * 1024 * 1024:
            return ToolResult(success=False, output="File too large (>10MB)")

        try:
            text = path.read_text(errors="replace")
            lines = text.splitlines(keepends=True)
            offset = arguments.get("offset", 0)
            limit = arguments.get("limit", 2000)
            selected = lines[offset : offset + limit]

            output = "".join(
                f"{i + offset + 1:4d} | {line}" for i, line in enumerate(selected)
            )
            total = len(lines)
            if offset + limit < total:
                output += f"\n... ({total - offset - limit} more lines)"

            return ToolResult(
                success=True,
                output=output,
                outcome={"file_read": str(path), "lines": len(selected)},
            )
        except Exception as e:
            return ToolResult(success=False, output=f"Error reading file: {e}")


class FileWriteTool(Tool):
    schema = ToolSchema(
        name="file_write",
        description="Write content to a file. Creates the file if it doesn't exist, overwrites if it does.",
        parameters={
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Path to the file to write",
                },
                "content": {
                    "type": "string",
                    "description": "Content to write to the file",
                },
                "append": {
                    "type": "boolean",
                    "description": "If true, append to file instead of overwriting",
                },
            },
            "required": ["path", "content"],
        },
        category="filesystem",
    )

    async def execute(self, arguments: dict[str, Any], context: ToolContext) -> ToolResult:
        path = Path(arguments["path"]).expanduser().resolve()
        content = arguments["content"]
        append = arguments.get("append", False)

        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            mode = "a" if append else "w"
            with open(path, mode) as f:
                f.write(content)
            return ToolResult(
                success=True,
                output=f"{'Appended to' if append else 'Wrote'} {path} ({len(content)} chars)",
                outcome={"file_written": str(path), "chars": len(content)},
            )
        except Exception as e:
            return ToolResult(success=False, output=f"Error writing file: {e}")


class FileSearchTool(Tool):
    schema = ToolSchema(
        name="file_search",
        description="Search for files by name pattern (glob). Returns matching file paths.",
        parameters={
            "type": "object",
            "properties": {
                "pattern": {
                    "type": "string",
                    "description": "Glob pattern to match (e.g., '*.py', '**/*.md')",
                },
                "directory": {
                    "type": "string",
                    "description": "Directory to search in (default: workspace root)",
                },
            },
            "required": ["pattern"],
        },
        category="filesystem",
    )

    async def execute(self, arguments: dict[str, Any], context: ToolContext) -> ToolResult:
        pattern = arguments["pattern"]
        directory = Path(
            arguments.get("directory", context.workspace)
        ).expanduser().resolve()

        if not directory.exists():
            return ToolResult(success=False, output=f"Directory not found: {directory}")

        matches = sorted(directory.glob(pattern))[:100]  # Cap at 100 results
        if not matches:
            return ToolResult(success=True, output="No files found matching pattern.")

        output = "\n".join(str(m) for m in matches)
        return ToolResult(
            success=True,
            output=output,
            outcome={"files_found": len(matches)},
        )


class TextSearchTool(Tool):
    schema = ToolSchema(
        name="text_search",
        description="Search for text content within files (like grep). Returns matching lines with context.",
        parameters={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Text or regex pattern to search for",
                },
                "directory": {
                    "type": "string",
                    "description": "Directory to search in",
                },
                "file_pattern": {
                    "type": "string",
                    "description": "Only search files matching this glob (e.g., '*.py')",
                },
            },
            "required": ["query"],
        },
        timeout_seconds=30,
        category="filesystem",
    )

    async def execute(self, arguments: dict[str, Any], context: ToolContext) -> ToolResult:
        import re

        query = arguments["query"]
        directory = Path(
            arguments.get("directory", context.workspace)
        ).expanduser().resolve()
        file_pattern = arguments.get("file_pattern", "*")

        try:
            pattern = re.compile(query, re.IGNORECASE)
        except re.error:
            pattern = re.compile(re.escape(query), re.IGNORECASE)

        results = []
        files_searched = 0

        for fpath in directory.rglob(file_pattern):
            if not fpath.is_file():
                continue
            if fpath.stat().st_size > 1024 * 1024:  # Skip files > 1MB
                continue
            files_searched += 1
            if files_searched > 1000:
                break
            try:
                text = fpath.read_text(errors="replace")
                for i, line in enumerate(text.splitlines(), 1):
                    if pattern.search(line):
                        results.append(f"{fpath}:{i}: {line.strip()}")
                        if len(results) >= 50:
                            break
            except Exception:
                continue
            if len(results) >= 50:
                break

        if not results:
            return ToolResult(
                success=True,
                output=f"No matches found in {files_searched} files.",
            )

        output = "\n".join(results)
        if len(results) >= 50:
            output += "\n... (results truncated at 50 matches)"

        return ToolResult(
            success=True,
            output=output,
            outcome={"matches": len(results), "files_searched": files_searched},
        )


def register(registry: ToolRegistry):
    registry.register(FileReadTool())
    registry.register(FileWriteTool())
    registry.register(FileSearchTool())
    registry.register(TextSearchTool())
