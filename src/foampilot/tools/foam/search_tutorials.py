"""Search the tutorial index for matching OpenFOAM cases."""

from typing import Any

from foampilot import config
from foampilot.core.permissions import PermissionLevel
from foampilot.index.searcher import TutorialSearcher
from foampilot.tools.base import Tool, ToolResult
from foampilot.version.registry import VersionRegistry


class SearchTutorialsTool(Tool):
    """Search the OpenFOAM tutorial index for cases that match a simulation request."""

    name = "search_tutorials"
    description = (
        "Search the OpenFOAM tutorial index to find the closest matching case "
        "for a given solver and physics requirements. Returns ranked matches with paths."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "solver": {
                "type": "string",
                "description": "OpenFOAM solver binary name (e.g., 'simpleFoam', 'interFoam')",
            },
            "physics_tags": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Required physics tags (e.g., ['incompressible', 'turbulent', 'steady'])",
            },
            "keywords": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Free-text keywords (e.g., ['pipe', 'channel', 'backward facing step'])",
            },
            "top_n": {
                "type": "integer",
                "description": "Maximum number of results to return (default 5)",
                "default": 5,
            },
        },
    }
    permission_level = PermissionLevel.AUTO

    def __init__(self, index_dir=None) -> None:
        self._index_dir = index_dir

    def execute(
        self,
        solver: str | None = None,
        physics_tags: list[str] | None = None,
        keywords: list[str] | None = None,
        top_n: int = 5,
        **kwargs: Any,
    ) -> ToolResult:
        try:
            version = VersionRegistry.get().active().VERSION
            searcher = TutorialSearcher(
                index_dir=self._index_dir or config.INDEX_DIR,
                version=version,
            )
            results = searcher.search(
                solver=solver,
                physics_tags=physics_tags,
                keywords=keywords,
                top_n=top_n,
            )
        except Exception as exc:
            return ToolResult.fail(f"Search failed: {exc}")

        return ToolResult.ok(
            data={
                "count": len(results),
                "results": [
                    {
                        "path": r.entry.path,
                        "solver": r.entry.solver,
                        "physics_tags": r.entry.physics_tags,
                        "turbulence_model": r.entry.turbulence_model,
                        "mesh_type": r.entry.mesh_type,
                        "has_heat_transfer": r.entry.has_heat_transfer,
                        "has_multiphase": r.entry.has_multiphase,
                        "description": r.entry.description,
                        "score": round(r.score, 3),
                        "match_reasons": r.match_reasons,
                    }
                    for r in results
                ],
            },
            token_hint=300,
        )
