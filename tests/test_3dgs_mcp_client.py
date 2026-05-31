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

    def test_create_render_calls_3dgs_tool(self) -> None:
        rpc_result = {
            "result": {
                "ok": True,
                "source": "3dgs:mcp",
                "session_id": "abc",
                "render_url": "http://127.0.0.1:8090/viewer/sessions/abc",
                "created_at": 1.0,
                "expires_at": 601.0,
                "ttl_sec": 600,
                "asset": {"model_url": "http://127.0.0.1:8090/assets/source/object.ply"},
            }
        }

        with patch.object(self.client, "_rpc", return_value=rpc_result) as rpc:
            result = self.client.create_render(" object.ply ", quality="balanced", ttl_sec=60)

        self.assertEqual(result["render_url"], rpc_result["result"]["render_url"])
        rpc.assert_called_once_with(
            "tools/call",
            {
                "name": "3dgs.create_render",
                "arguments": {
                    "filename": "object.ply",
                    "quality": "balanced",
                    "ttl_sec": 60,
                },
            },
        )

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


if __name__ == "__main__":
    unittest.main()
