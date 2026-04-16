"""Tests for tool registry and built-in tools."""

from __future__ import annotations

import os
import tempfile

import pytest

from kira.core.models import ToolContext


class TestToolRegistry:
    def test_load_builtin(self, tool_registry):
        schemas = tool_registry.list_schemas()
        assert len(schemas) >= 18  # At least our known tools

    def test_all_expected_tools_present(self, tool_registry):
        names = {s.name for s in tool_registry.list_schemas()}
        expected = {
            "file_read",
            "file_write",
            "file_search",
            "text_search",
            "terminal",
            "web_fetch",
            "web_search",
            "gmail_search",
            "gmail_read",
            "gmail_send",
            "gmail_draft",
            "gmail_label",
            "gmail_list_labels",
            "note_save",
            "note_search",
            "note_list",
            "note_read",
            "system_info",
            "stock_price",
            "stock_detail",
            "market_overview",
            "stock_screener",
        }
        assert expected.issubset(names), f"Missing tools: {expected - names}"

    def test_get_tool(self, tool_registry):
        tool = tool_registry.get("file_read")
        assert tool is not None
        assert tool.schema.name == "file_read"

    def test_get_nonexistent(self, tool_registry):
        assert tool_registry.get("nonexistent_tool") is None

    def test_filter_by_category(self, tool_registry):
        finance = tool_registry.list_schemas(categories=["finance"])
        assert all(s.category == "finance" for s in finance)
        assert len(finance) >= 4

    @pytest.mark.asyncio
    async def test_execute_unknown_tool(self, tool_registry):
        ctx = ToolContext(session_id="test", workspace="/tmp")
        result = await tool_registry.execute("nonexistent", {}, ctx)
        assert not result.success
        assert "Unknown tool" in result.output

    @pytest.mark.asyncio
    async def test_execute_invalid_args(self, tool_registry):
        ctx = ToolContext(session_id="test", workspace="/tmp")
        result = await tool_registry.execute("file_read", {}, ctx)  # Missing 'path'
        assert not result.success
        assert "Invalid arguments" in result.output

    def test_tool_schemas_have_descriptions(self, tool_registry):
        for schema in tool_registry.list_schemas():
            assert schema.description, f"Tool {schema.name} has no description"
            assert len(schema.description) > 10, f"Tool {schema.name} description too short"

    def test_gmail_send_requires_approval(self, tool_registry):
        tool = tool_registry.get("gmail_send")
        assert tool.schema.requires_approval is True

    def test_terminal_requires_approval(self, tool_registry):
        tool = tool_registry.get("terminal")
        assert tool.schema.requires_approval is True


class TestFileTools:
    @pytest.mark.asyncio
    async def test_file_read(self, tool_registry):
        # Create a temp file
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("line 1\nline 2\nline 3\n")
            path = f.name

        ctx = ToolContext(session_id="test", workspace="/tmp")
        result = await tool_registry.execute("file_read", {"path": path}, ctx)
        assert result.success
        assert "line 1" in result.output
        assert "line 2" in result.output
        os.unlink(path)

    @pytest.mark.asyncio
    async def test_file_read_not_found(self, tool_registry):
        ctx = ToolContext(session_id="test", workspace="/tmp")
        result = await tool_registry.execute(
            "file_read", {"path": "/tmp/nonexistent_file_xyz.txt"}, ctx
        )
        assert not result.success
        assert "not found" in result.output.lower()

    @pytest.mark.asyncio
    async def test_file_write(self, tool_registry):
        path = os.path.join(tempfile.mkdtemp(), "test_output.txt")
        ctx = ToolContext(session_id="test", workspace="/tmp")
        result = await tool_registry.execute(
            "file_write", {"path": path, "content": "hello world"}, ctx
        )
        assert result.success
        assert os.path.exists(path)
        assert open(path).read() == "hello world"

    @pytest.mark.asyncio
    async def test_file_write_append(self, tool_registry):
        path = os.path.join(tempfile.mkdtemp(), "append_test.txt")
        ctx = ToolContext(session_id="test", workspace="/tmp")
        await tool_registry.execute("file_write", {"path": path, "content": "first "}, ctx)
        await tool_registry.execute(
            "file_write", {"path": path, "content": "second", "append": True}, ctx
        )
        assert open(path).read() == "first second"

    @pytest.mark.asyncio
    async def test_file_search(self, tool_registry):
        tmpdir = tempfile.mkdtemp()
        open(os.path.join(tmpdir, "test.py"), "w").close()
        open(os.path.join(tmpdir, "test.md"), "w").close()

        ctx = ToolContext(session_id="test", workspace=tmpdir)
        result = await tool_registry.execute(
            "file_search", {"pattern": "*.py", "directory": tmpdir}, ctx
        )
        assert result.success
        assert "test.py" in result.output
        assert "test.md" not in result.output

    @pytest.mark.asyncio
    async def test_text_search(self, tool_registry):
        tmpdir = tempfile.mkdtemp()
        with open(os.path.join(tmpdir, "code.py"), "w") as f:
            f.write("def hello():\n    return 'world'\n")

        ctx = ToolContext(session_id="test", workspace=tmpdir)
        result = await tool_registry.execute(
            "text_search", {"query": "hello", "directory": tmpdir}, ctx
        )
        assert result.success
        assert "hello" in result.output


class TestTerminalTool:
    @pytest.mark.asyncio
    async def test_blocked_command(self, tool_registry):
        ctx = ToolContext(session_id="test", workspace="/tmp")
        result = await tool_registry.execute("terminal", {"command": "rm -rf /"}, ctx)
        assert not result.success
        assert "Blocked" in result.output

    @pytest.mark.asyncio
    async def test_blocked_sudo(self, tool_registry):
        ctx = ToolContext(session_id="test", workspace="/tmp")
        result = await tool_registry.execute("terminal", {"command": "sudo rm something"}, ctx)
        assert not result.success


class TestSystemTool:
    @pytest.mark.asyncio
    async def test_system_info(self, tool_registry):
        ctx = ToolContext(session_id="test", workspace="/tmp")
        result = await tool_registry.execute("system_info", {}, ctx)
        assert result.success
        assert "OS:" in result.output
        assert "Disk" in result.output


class TestNoteTools:
    @pytest.mark.asyncio
    async def test_note_save_and_search(self, tool_registry):
        ctx = ToolContext(session_id="test", workspace="/tmp")

        # Save a note
        result = await tool_registry.execute(
            "note_save",
            {
                "title": "Test Note XYZ",
                "content": "This is a unique test note content.",
                "tags": ["test"],
            },
            ctx,
        )
        assert result.success
        assert "Note saved" in result.output

        # Search for it
        result = await tool_registry.execute("note_search", {"query": "unique test note"}, ctx)
        assert result.success
        assert "Test Note XYZ" in result.output

    @pytest.mark.asyncio
    async def test_note_list(self, tool_registry):
        ctx = ToolContext(session_id="test", workspace="/tmp")
        result = await tool_registry.execute("note_list", {}, ctx)
        assert result.success
