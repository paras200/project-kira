"""Web tools — fetch URLs and extract content."""

from __future__ import annotations

import re
from typing import Any

import httpx

from kira.core.models import ToolContext, ToolResult, ToolSchema
from kira.tools.registry import Tool, ToolRegistry


class WebFetchTool(Tool):
    schema = ToolSchema(
        name="web_fetch",
        description=(
            "Fetch a URL and return its text content. "
            "Strips HTML tags and returns readable text."
        ),
        parameters={
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "The URL to fetch",
                },
                "max_length": {
                    "type": "integer",
                    "description": "Maximum characters to return (default: 10000)",
                },
            },
            "required": ["url"],
        },
        timeout_seconds=30,
        category="web",
    )

    def _strip_html(self, html: str) -> str:
        """Basic HTML to text conversion."""
        # Remove script and style blocks
        text = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL)
        text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.DOTALL)
        # Convert common elements
        text = re.sub(r"<br\s*/?>", "\n", text)
        text = re.sub(r"</?p>", "\n", text)
        text = re.sub(r"</?div>", "\n", text)
        text = re.sub(r"<h[1-6][^>]*>", "\n## ", text)
        text = re.sub(r"</h[1-6]>", "\n", text)
        text = re.sub(r"<li[^>]*>", "- ", text)
        # Strip remaining tags
        text = re.sub(r"<[^>]+>", "", text)
        # Clean up whitespace
        text = re.sub(r"\n{3,}", "\n\n", text)
        text = re.sub(r"[ \t]+", " ", text)
        # Decode common entities
        text = text.replace("&amp;", "&")
        text = text.replace("&lt;", "<")
        text = text.replace("&gt;", ">")
        text = text.replace("&quot;", '"')
        text = text.replace("&#39;", "'")
        text = text.replace("&nbsp;", " ")
        return text.strip()

    async def execute(self, arguments: dict[str, Any], context: ToolContext) -> ToolResult:
        url = arguments["url"]
        max_length = arguments.get("max_length", 10_000)

        try:
            async with httpx.AsyncClient(
                follow_redirects=True, timeout=20.0
            ) as client:
                resp = await client.get(
                    url,
                    headers={"User-Agent": "Kira/0.1 (Personal AI Agent)"},
                )
                resp.raise_for_status()

            content_type = resp.headers.get("content-type", "")
            if "text/html" in content_type:
                text = self._strip_html(resp.text)
            else:
                text = resp.text

            if len(text) > max_length:
                text = text[:max_length] + "\n...(truncated)"

            return ToolResult(
                success=True,
                output=text,
                outcome={"url": url, "chars": len(text)},
            )
        except httpx.HTTPStatusError as e:
            return ToolResult(
                success=False, output=f"HTTP {e.response.status_code}: {url}"
            )
        except Exception as e:
            return ToolResult(success=False, output=f"Failed to fetch {url}: {e}")


def register(registry: ToolRegistry):
    registry.register(WebFetchTool())
