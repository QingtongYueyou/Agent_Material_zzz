from __future__ import annotations

import importlib
import json
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


class WorkflowMCPArtifactTests(unittest.TestCase):
    def setUp(self) -> None:
        _install_tool_dependency_stubs()

    def _install_mcp_stubs(self) -> dict[str, object]:
        calls: dict[str, object] = {"metadata": [], "routes": [], "gateway": []}
        metadata = {
            "file_id": "file_dos",
            "filename": "dos.txt",
            "extension": ".txt",
            "mime_type": "text/plain",
            "size_bytes": 7,
            "source": "user_upload",
        }

        upload_store = types.ModuleType("core.upload_store")

        def get_file_metadata(file_id: str) -> dict[str, object]:
            calls["metadata"].append(file_id)
            return dict(metadata, file_id=file_id)

        def read_file_base64(file_id: str) -> tuple[dict[str, object], str]:
            return dict(metadata, file_id=file_id), "ZG9zZGF0YQ=="

        upload_store.get_file_metadata = get_file_metadata
        upload_store.read_file_base64 = read_file_base64
        sys.modules["core.upload_store"] = upload_store

        mcp_router = types.ModuleType("core.mcp_router")

        def resolve_route(intent: str, input_type: str, route_metadata: dict[str, object]) -> dict[str, object]:
            calls["routes"].append((intent, input_type, route_metadata["file_id"]))
            return {"title": "DOS visualization", "server": "dos-mcp-server", "file_tool": "dos.dos_file"}

        mcp_router.resolve_route = resolve_route
        sys.modules["core.mcp_router"] = mcp_router

        mcp_gateway = types.ModuleType("core.mcp_gateway")

        def call_tool(server_name: str, tool_name: str, arguments: dict[str, object]) -> dict[str, object]:
            calls["gateway"].append((server_name, tool_name, arguments))
            return {"render_url": "https://render.example/dos", "expires_at": 123.0}

        def extract_render_url(result: object) -> str:
            return result["render_url"]

        mcp_gateway.call_tool = call_tool
        mcp_gateway.extract_render_url = extract_render_url
        sys.modules["core.mcp_gateway"] = mcp_gateway
        return calls

    def test_render_with_mcp_artifact_is_aggregated_into_final_event(self) -> None:
        calls = self._install_mcp_stubs()
        workflow = importlib.import_module("core.workflow")

        recorded_messages: list[list[dict[str, object]]] = []

        def fake_llm(messages: list[dict[str, object]], **kwargs) -> dict[str, object]:
            recorded_messages.append(messages)
            if len(recorded_messages) == 1:
                return {
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "call_1",
                            "function": {
                                "name": "render_with_mcp",
                                "arguments": json.dumps(
                                    {"intent": "dos", "input_type": "file", "file_id": "file_dos"}
                                ),
                            },
                        }
                    ],
                }
            if len(recorded_messages) == 2:
                return {"content": "done", "tool_calls": []}
            return {"content": "已生成 DOS 可视化。", "tool_calls": []}

        with patch.object(workflow, "create_chat_completion", side_effect=fake_llm):
            events = list(workflow.WorkflowOrchestrator().run_stream("画 DOS", file_ids=["file_dos"]))

        final = events[-1]
        self.assertEqual(final["type"], "final")
        self.assertEqual(len(final["artifacts"]), 1)
        artifact = final["artifacts"][0]
        self.assertEqual(artifact["kind"], "mcp_visualization")
        self.assertEqual(artifact["intent"], "dos")
        self.assertEqual(artifact["source_file_id"], "file_dos")
        self.assertEqual(artifact["render_url"], "https://render.example/dos")
        self.assertEqual(calls["metadata"], ["file_dos", "file_dos"])
        self.assertEqual(calls["routes"], [("dos", "file", "file_dos")])
        self.assertEqual(calls["gateway"][0][0], "dos-mcp-server")
        self.assertEqual(calls["gateway"][0][1], "dos.dos_file")
        self.assertEqual(calls["gateway"][0][2]["content_base64"], "ZG9zZGF0YQ==")
        self.assertIn("file_dos", json.dumps(recorded_messages[0], ensure_ascii=False))

    def test_no_file_query_keeps_legacy_final_shape_with_empty_artifacts(self) -> None:
        sys.modules.pop("core.upload_store", None)
        workflow = importlib.import_module("core.workflow")

        with patch.object(
            workflow,
            "create_chat_completion",
            return_value={"content": "普通回答", "tool_calls": []},
        ):
            events = list(workflow.WorkflowOrchestrator().run_stream("你好"))

        final = events[-1]
        self.assertEqual(final["type"], "final")
        self.assertEqual(final["answer"], "普通回答")
        self.assertEqual(final["artifacts"], [])


if __name__ == "__main__":
    unittest.main()
