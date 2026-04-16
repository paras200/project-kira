"""Notes tool — personal knowledge base. Save, search, and retrieve notes."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from kira.core.models import ToolContext, ToolResult, ToolSchema
from kira.tools.registry import Tool, ToolRegistry

NOTES_DIR = Path.home() / ".kira" / "notes"


class NoteSaveTool(Tool):
    schema = ToolSchema(
        name="note_save",
        description=(
            "Save a note to your personal knowledge base. "
            "Notes are plain text files organized by tags. "
            "Use this to save research, bookmarks, ideas, or anything worth remembering."
        ),
        parameters={
            "type": "object",
            "properties": {
                "title": {
                    "type": "string",
                    "description": "Short title for the note",
                },
                "content": {
                    "type": "string",
                    "description": "The note content (markdown supported)",
                },
                "tags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Tags for categorization (e.g., ['research', 'ai'])",
                },
            },
            "required": ["title", "content"],
        },
        category="notes",
    )

    async def execute(self, arguments: dict[str, Any], context: ToolContext) -> ToolResult:
        title = arguments["title"]
        content = arguments["content"]
        tags = arguments.get("tags", [])

        NOTES_DIR.mkdir(parents=True, exist_ok=True)

        # Generate filename from title
        import re

        slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        filename = f"{timestamp}-{slug}.md"
        filepath = NOTES_DIR / filename

        # Build note with frontmatter
        tags_str = ", ".join(tags) if tags else ""
        note = f"# {title}\n\n"
        if tags_str:
            note += f"Tags: {tags_str}\n"
        note += f"Date: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}\n\n"
        note += content + "\n"

        filepath.write_text(note)

        return ToolResult(
            success=True,
            output=f"Note saved: {filename}",
            outcome={"note_saved": str(filepath), "title": title},
        )


class NoteSearchTool(Tool):
    schema = ToolSchema(
        name="note_search",
        description=(
            "Search your personal notes by keyword. "
            "Returns matching notes with titles and previews."
        ),
        parameters={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query (searches titles and content)",
                },
            },
            "required": ["query"],
        },
        category="notes",
    )

    async def execute(self, arguments: dict[str, Any], context: ToolContext) -> ToolResult:
        query = arguments["query"].lower()

        if not NOTES_DIR.exists():
            return ToolResult(success=True, output="No notes yet.")

        matches = []
        for note_file in sorted(NOTES_DIR.glob("*.md"), reverse=True):
            content = note_file.read_text()
            if query in content.lower():
                # Extract title (first line)
                title = content.split("\n")[0].lstrip("# ").strip()
                preview = content[:200].replace("\n", " ")
                matches.append(f"- **{title}** ({note_file.name})\n  {preview}...")

            if len(matches) >= 10:
                break

        if not matches:
            return ToolResult(success=True, output=f"No notes matching: {query}")

        return ToolResult(
            success=True,
            output=f"Found {len(matches)} note(s):\n\n" + "\n\n".join(matches),
            outcome={"notes_found": len(matches)},
        )


class NoteListTool(Tool):
    schema = ToolSchema(
        name="note_list",
        description="List all saved notes, most recent first.",
        parameters={
            "type": "object",
            "properties": {
                "limit": {
                    "type": "integer",
                    "description": "Max notes to list (default: 20)",
                },
            },
        },
        category="notes",
    )

    async def execute(self, arguments: dict[str, Any], context: ToolContext) -> ToolResult:
        limit = arguments.get("limit", 20)

        if not NOTES_DIR.exists():
            return ToolResult(success=True, output="No notes yet.")

        notes = sorted(NOTES_DIR.glob("*.md"), reverse=True)[:limit]
        if not notes:
            return ToolResult(success=True, output="No notes yet.")

        lines = [f"Notes ({len(notes)} shown):\n"]
        for note_file in notes:
            content = note_file.read_text()
            title = content.split("\n")[0].lstrip("# ").strip()
            size = note_file.stat().st_size
            lines.append(f"- {title} ({note_file.name}, {size}B)")

        return ToolResult(
            success=True,
            output="\n".join(lines),
            outcome={"notes_count": len(notes)},
        )


class NoteReadTool(Tool):
    schema = ToolSchema(
        name="note_read",
        description="Read a specific note by filename.",
        parameters={
            "type": "object",
            "properties": {
                "filename": {
                    "type": "string",
                    "description": "The note filename (e.g., '20260416-my-note.md')",
                },
            },
            "required": ["filename"],
        },
        category="notes",
    )

    async def execute(self, arguments: dict[str, Any], context: ToolContext) -> ToolResult:
        filename = arguments["filename"]
        filepath = NOTES_DIR / filename

        if not filepath.exists():
            return ToolResult(success=False, output=f"Note not found: {filename}")

        content = filepath.read_text()
        return ToolResult(
            success=True,
            output=content,
            outcome={"note_read": filename},
        )


def register(registry: ToolRegistry):
    registry.register(NoteSaveTool())
    registry.register(NoteSearchTool())
    registry.register(NoteListTool())
    registry.register(NoteReadTool())
