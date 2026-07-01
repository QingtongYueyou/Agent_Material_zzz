from __future__ import annotations

import time
import unittest

from core import mcp_client


class MCPClientParsingTests(unittest.TestCase):
    def test_decode_plain_json_response(self) -> None:
        payload = '{"jsonrpc":"2.0","id":1,"result":{"ok":true}}'

        data = mcp_client._decode_json_response(payload)

        self.assertEqual(data["result"]["ok"], True)

    def test_decode_sse_json_response(self) -> None:
        payload = 'event: message\ndata: {"jsonrpc":"2.0","id":1,"result":{"ok":true}}\n\n'

        data = mcp_client._decode_json_response(payload)

        self.assertEqual(data["result"]["ok"], True)

    def test_extract_render_url_from_content_text(self) -> None:
        result = {
            "content": [
                {
                    "type": "text",
                    "text": '{"render_url":"http://example.test/view?render_id=abc"}',
                }
            ]
        }

        render_url = mcp_client._extract_render_url(result)

        self.assertEqual(render_url, "http://example.test/view?render_id=abc")

    def test_render_url_freshness_uses_skew(self) -> None:
        self.assertTrue(mcp_client.is_render_url_fresh(time.time() + 120, skew_sec=30))
        self.assertFalse(mcp_client.is_render_url_fresh(time.time() + 10, skew_sec=30))


if __name__ == "__main__":
    unittest.main()
