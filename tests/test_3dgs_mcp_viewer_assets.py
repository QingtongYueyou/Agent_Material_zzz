from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from mcp_3dgs import server


class ThreeDGSViewerAssetTests(unittest.TestCase):
    def test_mcp_endpoint_requires_api_key_when_configured(self) -> None:
        client = TestClient(server.app)
        payload = {"jsonrpc": "2.0", "id": "1", "method": "tools/list", "params": {}}

        with patch.object(server, "THREEDGS_MCP_API_KEY", "secret"):
            unauthorized = client.post("/mcp", json=payload)
            authorized = client.post("/mcp", json=payload, headers={"visualization-api-key": "secret"})

        self.assertEqual(unauthorized.status_code, 200)
        self.assertEqual(unauthorized.json()["error"]["code"], -32001)
        self.assertEqual(authorized.status_code, 200)
        self.assertIn("result", authorized.json())

    def test_unbuilt_viewer_dist_returns_clear_nonblank_html(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            dist_dir = Path(tmp) / "dist"

            with patch.object(server, "VIEWER_INDEX_HTML", dist_dir / "index.html"):
                html = server.viewer_session("session-abc")

        self.assertIn("3DGS viewer app is not built", html)
        self.assertIn('id="root"', html)
        self.assertIn('data-session-id="session-abc"', html)
        self.assertIn("npm run build", html)

    def test_built_viewer_index_rewrites_hashed_asset_urls(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            dist_dir = Path(tmp) / "dist"
            assets_dir = dist_dir / "assets"
            assets_dir.mkdir(parents=True)
            (assets_dir / "index-Bw9QmF.js").write_text("console.log('viewer');", encoding="utf-8")
            (assets_dir / "index-Bw9QmF.css").write_text("body{}", encoding="utf-8")
            index_html = dist_dir / "index.html"
            index_html.write_text(
                """<!doctype html>
<html lang="en">
<head>
  <link rel="stylesheet" crossorigin href="/assets/index-Bw9QmF.css">
</head>
<body>
  <div id="root"></div>
  <script type="module" crossorigin src="/assets/index-Bw9QmF.js"></script>
</body>
</html>""",
                encoding="utf-8",
            )

            with patch.object(server, "VIEWER_INDEX_HTML", index_html):
                html = server.viewer_session("session-xyz")

        self.assertIn('<main id="root" data-session-id="session-xyz"></main>', html)
        self.assertIn('href="/viewer/assets/index-Bw9QmF.css"', html)
        self.assertIn('src="/viewer/assets/index-Bw9QmF.js"', html)
        self.assertIn('id="session-config-url"', html)


if __name__ == "__main__":
    unittest.main()
