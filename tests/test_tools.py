from __future__ import annotations

import importlib
import sys
import types
import unittest
from unittest.mock import patch


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

    def test_search_results_are_cached_by_query_parameters(self) -> None:
        class FakeSymmetry:
            symbol = "Fm-3m"

        class FakeDoc:
            material_id = "mp-1"
            formula_pretty = "Si"
            band_gap = 1.23
            symmetry = FakeSymmetry()

        class FakeSummary:
            def __init__(self) -> None:
                self.calls = 0

            def search(self, **kwargs):
                self.calls += 1
                return [FakeDoc()]

        class FakeMPRester:
            def __init__(self) -> None:
                self.materials = types.SimpleNamespace(summary=FakeSummary())

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb) -> None:
                return None

        fake_mpr = FakeMPRester()
        self.tools._MP_SEARCH_CACHE.clear()
        self.tools._MP_BLOCKED_UNTIL = 0.0
        self.tools._MP_LAST_REQUEST_AT = 0.0

        with (
            patch.object(self.tools, "MP_API_KEY", "test-key"),
            patch.object(self.tools, "MPRester", return_value=fake_mpr),
            patch.object(self.tools, "_wait_for_mp_rate_limit"),
        ):
            first = self.tools.search_materials_by_criteria_raw(elements=["Si"], max_results=5)
            second = self.tools.search_materials_by_criteria_raw(elements=["Si"], max_results=5)

        self.assertTrue(first["ok"])
        self.assertTrue(second["ok"])
        self.assertEqual(second["source"], "search_cache")
        self.assertEqual(fake_mpr.materials.summary.calls, 1)

    def test_mp_block_error_opens_circuit_breaker(self) -> None:
        block_message = (
            "Your IP address or ASN has been temporarily blocked "
            "from accessing all MP services."
        )

        class BlockingSummary:
            def search(self, **kwargs):
                raise RuntimeError(block_message)

        class BlockingMPRester:
            def __init__(self) -> None:
                self.materials = types.SimpleNamespace(summary=BlockingSummary())

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb) -> None:
                return None

        self.tools._MP_SEARCH_CACHE.clear()
        self.tools._MP_BLOCKED_UNTIL = 0.0
        self.tools._MP_LAST_REQUEST_AT = 0.0

        with (
            patch.object(self.tools, "MP_API_KEY", "test-key"),
            patch.object(self.tools, "MPRester", return_value=BlockingMPRester()) as mpr,
            patch.object(self.tools, "_wait_for_mp_rate_limit"),
        ):
            first = self.tools.search_materials_by_criteria_raw(elements=["Li"], max_results=5)
            second = self.tools.search_materials_by_criteria_raw(elements=["Fe"], max_results=5)

        self.assertFalse(first["ok"])
        self.assertIn("Materials Project", first["error"])
        self.assertFalse(second["ok"])
        self.assertIn("已临时熔断", second["error"])
        self.assertEqual(mpr.call_count, 1)


if __name__ == "__main__":
    unittest.main()
