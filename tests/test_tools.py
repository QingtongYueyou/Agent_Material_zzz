from __future__ import annotations

import importlib
import sys
import types
import unittest


def _install_tool_dependency_stubs() -> None:
    agno_module = types.ModuleType("agno")
    agno_tools_module = types.ModuleType("agno.tools")

    def tool(*args, **kwargs):
        def decorator(func):
            return func

        return decorator

    agno_tools_module.tool = tool
    agno_module.tools = agno_tools_module
    sys.modules.setdefault("agno", agno_module)
    sys.modules.setdefault("agno.tools", agno_tools_module)

    mp_api_module = types.ModuleType("mp_api")
    mp_api_client_module = types.ModuleType("mp_api.client")

    class MPRester:
        def __init__(self, *args, **kwargs) -> None:
            pass

    mp_api_client_module.MPRester = MPRester
    mp_api_module.client = mp_api_client_module
    sys.modules.setdefault("mp_api", mp_api_module)
    sys.modules.setdefault("mp_api.client", mp_api_client_module)

    pymatgen_module = types.ModuleType("pymatgen")
    symmetry_module = types.ModuleType("pymatgen.symmetry")
    analyzer_module = types.ModuleType("pymatgen.symmetry.analyzer")

    class SpacegroupAnalyzer:
        def __init__(self, *args, **kwargs) -> None:
            pass

    analyzer_module.SpacegroupAnalyzer = SpacegroupAnalyzer
    symmetry_module.analyzer = analyzer_module
    pymatgen_module.symmetry = symmetry_module
    sys.modules.setdefault("pymatgen", pymatgen_module)
    sys.modules.setdefault("pymatgen.symmetry", symmetry_module)
    sys.modules.setdefault("pymatgen.symmetry.analyzer", analyzer_module)


class ToolsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        _install_tool_dependency_stubs()
        cls.tools = importlib.import_module("core.tools")

    def test_execute_openai_tool_requires_identifier(self) -> None:
        self.assertEqual(
            self.tools.execute_openai_tool("get_mp_structure", {"identifier": "   "}),
            {"error": "identifier is required"},
        )

    def test_execute_openai_tool_unknown_tool(self) -> None:
        self.assertEqual(
            self.tools.execute_openai_tool("missing_tool", {}),
            {"error": "Unknown tool: missing_tool"},
        )


if __name__ == "__main__":
    unittest.main()
