"""Web search tool — search the web via Brave Search API or DuckDuckGo HTML scraping."""

from __future__ import annotations

import re
from typing import Any

import httpx

from kira.core.models import ToolContext, ToolResult, ToolSchema
from kira.tools.registry import Tool, ToolRegistry


class WebSearchTool(Tool):
    schema = ToolSchema(
        name="web_search",
        description=(
            "Search the web and return results with titles, URLs, and snippets. "
            "Use this for research, finding current information, news, job listings, etc."
        ),
        parameters={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query",
                },
                "max_results": {
                    "type": "integer",
                    "description": "Maximum results to return (default: 5, max: 10)",
                },
            },
            "required": ["query"],
        },
        timeout_seconds=15,
        category="web",
    )

    async def execute(self, arguments: dict[str, Any], context: ToolContext) -> ToolResult:
        query = arguments["query"]
        max_results = min(arguments.get("max_results", 5), 10)

        import os

        brave_key = os.environ.get("BRAVE_SEARCH_API_KEY", "")

        if brave_key:
            return await self._brave_search(query, max_results, brave_key)
        else:
            return await self._duckduckgo_search(query, max_results)

    async def _brave_search(self, query: str, max_results: int, api_key: str) -> ToolResult:
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(
                    "https://api.search.brave.com/res/v1/web/search",
                    params={"q": query, "count": max_results},
                    headers={
                        "Accept": "application/json",
                        "X-Subscription-Token": api_key,
                    },
                )
                resp.raise_for_status()
                data = resp.json()

            results = data.get("web", {}).get("results", [])
            if not results:
                return ToolResult(success=True, output=f"No results for: {query}")

            lines = [f"Search results for: {query}\n"]
            for i, r in enumerate(results[:max_results], 1):
                lines.append(
                    f"{i}. {r.get('title', '?')}\n"
                    f"   {r.get('url', '')}\n"
                    f"   {r.get('description', '')}\n"
                )

            return ToolResult(
                success=True,
                output="\n".join(lines),
                outcome={"results_count": len(results)},
            )
        except Exception as e:
            return ToolResult(success=False, output=f"Brave search failed: {e}")

    async def _duckduckgo_search(self, query: str, max_results: int) -> ToolResult:
        """Fallback: scrape DuckDuckGo HTML (no API key needed)."""
        try:
            async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
                resp = await client.get(
                    "https://html.duckduckgo.com/html/",
                    params={"q": query},
                    headers={"User-Agent": "Kira/0.1 (Personal AI Agent)"},
                )
                resp.raise_for_status()

            html = resp.text
            # Extract results from DDG HTML
            results = []
            for match in re.finditer(
                r'<a rel="nofollow" class="result__a" href="([^"]+)"[^>]*>(.*?)</a>'
                r'.*?<a class="result__snippet"[^>]*>(.*?)</a>',
                html,
                re.DOTALL,
            ):
                url = match.group(1)
                title = re.sub(r"<[^>]+>", "", match.group(2)).strip()
                snippet = re.sub(r"<[^>]+>", "", match.group(3)).strip()
                if title and url:
                    results.append({"title": title, "url": url, "snippet": snippet})
                if len(results) >= max_results:
                    break

            if not results:
                return ToolResult(success=True, output=f"No results found for: {query}")

            lines = [f"Search results for: {query}\n"]
            for i, r in enumerate(results, 1):
                lines.append(f"{i}. {r['title']}\n   {r['url']}\n   {r['snippet']}\n")

            return ToolResult(
                success=True,
                output="\n".join(lines),
                outcome={"results_count": len(results)},
            )
        except Exception as e:
            return ToolResult(success=False, output=f"DuckDuckGo search failed: {e}")


def register(registry: ToolRegistry):
    registry.register(WebSearchTool())
