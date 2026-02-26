"""Tool registry — maps tool names to Tool implementations.

Build the default registry with build_default_registry(),
which assembles all available tools appropriate for the current version.
"""

from __future__ import annotations

from foampilot.tools.base import Tool


class ToolRegistry:
    """Manages a collection of Tool instances keyed by name."""

    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        """Register a tool instance."""
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def all(self) -> dict[str, Tool]:
        return dict(self._tools)

    def names(self) -> list[str]:
        return list(self._tools.keys())

    def __contains__(self, name: str) -> bool:
        return name in self._tools


def build_default_registry(docker_client=None) -> ToolRegistry:
    """Build and return the default tool registry with all standard tools.

    Args:
        docker_client: Optional Docker client for tools that execute commands.

    Returns:
        ToolRegistry populated with all available tools.
    """
    from foampilot.tools.foam.search_tutorials import SearchTutorialsTool
    from foampilot.tools.foam.copy_tutorial import CopyTutorialTool
    from foampilot.tools.foam.read_foam_file import ReadFoamFileTool
    from foampilot.tools.foam.edit_foam_dict import EditFoamDictTool
    from foampilot.tools.foam.write_foam_file import WriteFoamFileTool
    from foampilot.tools.foam.run_foam_cmd import RunFoamCmdTool
    from foampilot.tools.foam.check_mesh import CheckMeshTool
    from foampilot.tools.foam.parse_log import ParseLogTool
    from foampilot.tools.foam.extract_data import ExtractDataTool
    from foampilot.tools.general.bash import BashTool
    from foampilot.tools.general.read_file import ReadFileTool
    from foampilot.tools.general.write_file import WriteFileTool
    from foampilot.tools.general.str_replace import StrReplaceTool
    from foampilot.tools.viz.plot_residuals import PlotResidualsTool

    registry = ToolRegistry()

    # OpenFOAM tools
    registry.register(SearchTutorialsTool())
    registry.register(CopyTutorialTool())
    registry.register(ReadFoamFileTool())
    registry.register(EditFoamDictTool())
    registry.register(WriteFoamFileTool())
    registry.register(RunFoamCmdTool(docker_client=docker_client))
    registry.register(CheckMeshTool(docker_client=docker_client))
    registry.register(ParseLogTool())
    registry.register(ExtractDataTool())

    # General tools
    registry.register(BashTool())
    registry.register(ReadFileTool())
    registry.register(WriteFileTool())
    registry.register(StrReplaceTool())

    # Visualization
    registry.register(PlotResidualsTool())

    return registry
