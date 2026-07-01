from __future__ import annotations

import importlib
import unittest
from unittest.mock import patch


class ThreeDGSMCPClientTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.client = importlib.import_module("core.3dgs_mcp_client")

    def test_decode_plain_json_response(self) -> None:
        data = self.client._decode_json_response('{"jsonrpc":"2.0","result":{"ok":true}}')

        self.assertTrue(data["result"]["ok"])

    def test_decode_sse_json_response(self) -> None:
        data = self.client._decode_json_response(
            'event: message\ndata: {"jsonrpc":"2.0","result":{"ok":true}}\n\n'
        )

        self.assertTrue(data["result"]["ok"])

    def test_extract_result_from_content_text(self) -> None:
        result = {
            "content": [
                {
                    "type": "text",
                    "text": '{"ok":true,"render_url":"http://127.0.0.1:8090/viewer/sessions/abc"}',
                }
            ]
        }

        self.assertEqual(
            self.client._extract_result(result)["render_url"],
            "http://127.0.0.1:8090/viewer/sessions/abc",
        )

    def test_extract_result_prefers_structured_content(self) -> None:
        result = {
            "content": [{"type": "text", "text": '{"render_url":"text-url"}'}],
            "structuredContent": {"ok": True, "render_url": "structured-url"},
            "isError": False,
        }

        self.assertEqual(self.client._extract_result(result)["render_url"], "structured-url")

    def test_extract_result_raises_on_tool_error(self) -> None:
        result = {
            "content": [{"type": "text", "text": "No matching 3DGS splat asset found."}],
            "structuredContent": {"ok": False},
            "isError": True,
        }

        with self.assertRaisesRegex(self.client.ThreeDGSMCPClientError, "No matching"):
            self.client._extract_result(result)

    def test_initialize_sends_initialized_notification(self) -> None:
        with (
            patch.object(
                self.client,
                "_post_json",
                return_value=({"result": {"protocolVersion": "2025-06-18"}}, {"mcp-session-id": "sid-1"}),
            ) as post_json,
            patch.object(self.client, "_notify") as notify,
        ):
            session_id = self.client._initialize()

        self.assertEqual(session_id, "sid-1")
        self.assertEqual(post_json.call_args.args[0]["method"], "initialize")
        notify.assert_called_once_with("notifications/initialized", session_id="sid-1")

    def test_create_render_calls_3dgs_tool(self) -> None:
        rpc_result = {
            "result": {
                "content": [{"type": "text", "text": '{"ok":true}'}],
                "structuredContent": {
                    "ok": True,
                    "source": "3dgs:mcp",
                    "session_id": "abc",
                    "render_url": "http://127.0.0.1:8090/viewer/sessions/abc?token=t",
                    "created_at": 1.0,
                    "expires_at": 601.0,
                    "ttl_sec": 600,
                    "asset": {
                        "model_url": "http://127.0.0.1:8090/viewer/sessions/abc/assets/source/object.ply?token=t"
                    },
                },
                "isError": False,
            }
        }

        with (
            patch.object(self.client, "_ensure_session", return_value="mcp-session-1"),
            patch.object(self.client, "_rpc", return_value=rpc_result) as rpc,
        ):
            result = self.client.create_render(" object.ply ", quality="balanced", ttl_sec=60)

        self.assertEqual(result["render_url"], rpc_result["result"]["structuredContent"]["render_url"])
        rpc.assert_called_once_with(
            "tools/call",
            {
                "name": "3dgs.create_render",
                "arguments": {
                    "filename": "object.ply",
                    "quality": "balanced",
                    "render_profile": "performance",
                    "ttl_sec": 60,
                },
            },
            session_id="mcp-session-1",
        )

    def test_create_render_reinitializes_once_when_cached_session_is_unknown(self) -> None:
        rpc_result = {
            "result": {
                "content": [{"type": "text", "text": '{"ok":true}'}],
                "structuredContent": {
                    "ok": True,
                    "source": "3dgs:mcp",
                    "session_id": "abc",
                    "render_url": "http://127.0.0.1:8090/viewer/sessions/abc?token=t",
                    "created_at": 1.0,
                    "expires_at": 601.0,
                    "ttl_sec": 600,
                    "asset": {},
                },
                "isError": False,
            }
        }

        self.client._MCP_SESSION_ID = "stale-session"
        try:
            with (
                patch.object(self.client, "_initialize", side_effect=["new-session"]) as initialize,
                patch.object(
                    self.client,
                    "_rpc",
                    side_effect=[
                        self.client.ThreeDGSMCPSessionError("3DGS MCP HTTP 404: MCP session not found."),
                        rpc_result,
                    ],
                ) as rpc,
            ):
                result = self.client.create_render("object.ply", quality="auto")
        finally:
            self.client._MCP_SESSION_ID = None

        self.assertEqual(result["render_url"], rpc_result["result"]["structuredContent"]["render_url"])
        initialize.assert_called_once()
        self.assertEqual(rpc.call_count, 2)
        self.assertEqual(rpc.call_args_list[0].kwargs["session_id"], "stale-session")
        self.assertEqual(rpc.call_args_list[1].kwargs["session_id"], "new-session")

    def test_rpc_error_raises_clear_exception(self) -> None:
        with patch.object(
            self.client,
            "_decode_json_response",
            return_value={"error": {"code": -32602, "message": "bad filename"}},
        ):
            with patch.object(self.client.urllib.request, "urlopen") as urlopen:
                urlopen.return_value.__enter__.return_value.read.return_value = b"{}"

                with self.assertRaisesRegex(self.client.ThreeDGSMCPClientError, "bad filename"):
                    self.client._rpc("tools/call", {"name": "3dgs.create_render"})

    def test_rpc_session_error_raises_session_exception(self) -> None:
        with patch.object(
            self.client,
            "_decode_json_response",
            return_value={"error": {"code": -32002, "message": "MCP session is not initialized."}},
        ):
            with patch.object(self.client.urllib.request, "urlopen") as urlopen:
                urlopen.return_value.__enter__.return_value.read.return_value = b"{}"

                with self.assertRaises(self.client.ThreeDGSMCPSessionError):
                    self.client._rpc("tools/call", {"name": "3dgs.create_render"})


if __name__ == "__main__":
    unittest.main()
