"""Web search for OpenFOAM documentation, correlations, and troubleshooting."""

from typing import Any

from foampilot.core.permissions import PermissionLevel
from foampilot.tools.base import Tool, ToolResult


class WebSearchTool(Tool):
    """Search the web for OpenFOAM documentation, error messages, or engineering correlations."""

    name = "web_search"
    description = (
        "Search the web for information. Use for: OpenFOAM documentation, "
        "error message diagnosis, engineering correlations, or troubleshooting guidance."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "The search query",
            },
            "num_results": {
                "type": "integer",
                "description": "Number of results to return (default 5)",
                "default": 5,
            },
        },
        "required": ["query"],
    }
    permission_level = PermissionLevel.AUTO

    def execute(self, query: str, num_results: int = 5, **kwargs: Any) -> ToolResult:
        # Note: Actual web search would require an API key or library.
        # This is a stub that can be connected to any search provider.
        return ToolResult.fail(
            "Web search not configured. Add a search provider API key to enable this tool."
        )
