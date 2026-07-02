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
        # Force a re-import of core.workflow / core.tools so they pick up
        # the freshly stubbed core.mcp_router (with ROUTE_TABLE) installed
        # by ``_install_mcp_stubs`` in each test method.
        for name in ("core.workflow", "core.tools", "core.file_introspection",
                     "core.processor", "core.llm_client"):
            sys.modules.pop(name, None)
        import core as _core_pkg
        # Drop the cached module attribute on the parent package.
        for attr in ("workflow", "tools", "file_introspection",
                     "processor", "llm_client"):
            if hasattr(_core_pkg, attr):
                delattr(_core_pkg, attr)

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
        mcp_router.ROUTE_TABLE = {"dos": {}, "xrd": {}, "structure": {}}

        def resolve_route(intent: str, input_type: str, route_metadata: dict[str, object]) -> dict[str, object]:
            calls["routes"].append((intent, input_type, route_metadata["file_id"]))
            return {"title": "DOS visualization", "server": "dos-mcp-server", "file_tool": "dos.dos_file"}

        mcp_router.resolve_route = resolve_route
        sys.modules["core.mcp_router"] = mcp_router
        # Re-bind on the parent package so core.tools picks up the stub.
        core_pkg = sys.modules.get("core")
        if core_pkg is not None:
            setattr(core_pkg, "mcp_router", mcp_router)

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
        self.assertEqual(calls["metadata"], ["file_dos", "file_dos", "file_dos"])
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

    def test_render_with_mcp_failure_uses_mcp_error_code(self) -> None:
        workflow = importlib.import_module("core.workflow")

        def fake_llm(messages: list[dict[str, object]], **kwargs) -> dict[str, object]:
            return {
                "content": None,
                "tool_calls": [
                    {
                        "id": "call_1",
                        "function": {
                            "name": "render_with_mcp",
                            "arguments": json.dumps(
                                {
                                    "intent": "missing_intent",
                                    "input_type": "file",
                                    "file_id": "file_dos",
                                }
                            ),
                        },
                    }
                ],
            }

        with patch.object(workflow, "create_chat_completion", side_effect=fake_llm):
            events = list(workflow.WorkflowOrchestrator().run_stream("render"))

        render_step = next(
            event for event in events if event.get("type") == "step_end" and event.get("step") == "render_with_mcp"
        )
        final = events[-1]
        final_render_step = next(
            step for step in final["step_results"] if step["step_name"] == "render_with_mcp"
        )

        self.assertEqual(render_step["status"], "failed")
        self.assertEqual(final_render_step["error_code"], "MCP_RENDER_FAILED")

    # ---- Speed optimization: parallel tool execution ----
    def test_parallel_tool_execution_preserves_order_and_aggregates_results(self) -> None:
        """Two ``render_with_mcp`` calls in one round should run concurrently
        and still land in the original order in messages, step_results, and
        the final artifacts list.
        """
        calls = self._install_mcp_stubs()
        workflow = importlib.import_module("core.workflow")
        from core import tools as core_tools

        # Track execution timings to assert parallel execution.
        # If the two tools ran serially, the second start would always be
        # after the first end. With a 100ms barrier on each, parallel
        # execution should still complete in ~100ms total, serial in ~200ms.
        import threading
        import time

        barrier = threading.Barrier(2, timeout=2.0)
        start_times: list[float] = []
        end_times: list[float] = []

        original_execute = core_tools._execute_render_with_mcp

        def wrapped_execute(arguments: dict[str, object]) -> dict[str, object]:
            start_times.append(time.time())
            result = original_execute(arguments)
            time.sleep(0.1)  # simulate slow tool
            end_times.append(time.time())
            barrier.wait()  # both should reach this point
            return result

        recorded_messages: list[list[dict[str, object]]] = []

        def fake_llm(messages: list[dict[str, object]], **kwargs) -> dict[str, object]:
            recorded_messages.append(messages)
            if len(recorded_messages) == 1:
                return {
                    "content": "好的, 画两个",
                    "tool_calls": [
                        {
                            "id": "call_a",
                            "function": {
                                "name": "render_with_mcp",
                                "arguments": json.dumps(
                                    {"intent": "dos", "input_type": "file", "file_id": "file_dos"}
                                ),
                            },
                        },
                        {
                            "id": "call_b",
                            "function": {
                                "name": "render_with_mcp",
                                "arguments": json.dumps(
                                    {"intent": "xrd", "input_type": "file", "file_id": "file_dos"}
                                ),
                            },
                        },
                    ],
                }
            return {"content": "done", "tool_calls": []}

        with patch.object(core_tools, "_execute_render_with_mcp",
                          side_effect=wrapped_execute), \
             patch.object(workflow, "create_chat_completion", side_effect=fake_llm):
            events = list(workflow.WorkflowOrchestrator().run_stream("画 DOS 和 XRD", file_ids=["file_dos"]))

        # Two tool messages in round 2, in the original call_a → call_b order.
        round_2 = recorded_messages[1]
        tool_msgs = [m for m in round_2 if m.get("role") == "tool"]
        self.assertEqual(len(tool_msgs), 2)
        self.assertEqual([m["tool_call_id"] for m in tool_msgs], ["call_a", "call_b"])

        # Both render steps appear in step_results in the original order.
        final = events[-1]
        render_steps = [s for s in final["step_results"] if s["step_name"] == "render_with_mcp"]
        self.assertEqual(len(render_steps), 2)
        self.assertEqual([s["status"] for s in render_steps], ["success", "success"])

        # Both artifacts present and in original order.
        self.assertEqual(len(final["artifacts"]), 2)
        self.assertEqual([a["intent"] for a in final["artifacts"]], ["dos", "xrd"])

        # Parallelism: the slower of the two start_times should be very close
        # to the first start_time (within 50ms), proving the second call
        # started before the first finished.
        self.assertGreater(len(start_times), 0)
        self.assertGreater(len(end_times), 0)
        gap = max(start_times) - min(start_times)
        self.assertLess(gap, 0.05, f"tools appear to have started serially (gap={gap:.3f}s)")

    # ---- Speed optimization: skip duplicate LLM composition when artifacts exist ----
    def test_skip_composition_when_artifacts_exist(self) -> None:
        """When ``render_with_mcp`` produces an artifact, the workflow must
        skip the second LLM ``_final_answer_from_context`` call and use the
        round-1 content as the final answer. The ``answer_composition`` step
        records ``source="artifact_self_describing"`` to make this observable.
        """
        self._install_mcp_stubs()
        workflow = importlib.import_module("core.workflow")

        # Patch ``_final_answer_from_context`` to record calls; if it's
        # invoked at all, this test should fail.
        composition_calls: list[int] = []
        original_compose = workflow._final_answer_from_context

        def spy_compose(ctx):
            composition_calls.append(1)
            return original_compose(ctx)

        recorded_messages: list[list[dict[str, object]]] = []

        def fake_llm(messages: list[dict[str, object]], **kwargs) -> dict[str, object]:
            recorded_messages.append(messages)
            if len(recorded_messages) == 1:
                return {
                    "content": "好的, 这就画",
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
            return {"content": "已生成 DOS 可视化，请查看下方结果。", "tool_calls": []}

        with patch.object(workflow, "_final_answer_from_context", side_effect=spy_compose), \
             patch.object(workflow, "create_chat_completion", side_effect=fake_llm):
            events = list(workflow.WorkflowOrchestrator().run_stream("画 DOS", file_ids=["file_dos"]))

        final = events[-1]
        # The LLM's round-2 content is the final answer — no recomposition call
        # happens, even though artifacts are now in context.
        self.assertEqual(final["answer"], "已生成 DOS 可视化，请查看下方结果。")
        # No composition call should have been made.
        self.assertEqual(composition_calls, [])
        # The answer_composition step records the skip — data is on the
        # yielded step_end event (the final-event step_results serialization
        # does not include ``data``).
        composition_step_ends = [
            e for e in events
            if e.get("type") == "step_end" and e.get("step") == "answer_composition"
        ]
        self.assertEqual(len(composition_step_ends), 1)
        self.assertEqual(composition_step_ends[0]["data"]["source"], "artifact_self_describing")


if __name__ == "__main__":
    unittest.main()
