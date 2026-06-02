from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from unittest.mock import patch

from fastapi.testclient import TestClient

from config.settings import BASE_DIR
from services.three_dgs_mcp import server


class ThreeDGSRenderingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        from services.three_dgs_mcp import rendering

        cls.rendering = rendering

    def setUp(self) -> None:
        self.rendering.sessions.clear()

    def tearDown(self) -> None:
        self.rendering.sessions.clear()

    def _token_from_url(self, render_url: str) -> str:
        token = parse_qs(urlparse(render_url).query).get("token", [""])[0]
        self.assertTrue(token)
        return token

    def test_asset_route_path_stays_inside_splat_files(self) -> None:
        path = self.rendering.resolve_asset_relative_path("source/object.ply")
        self.assertEqual(path.name, "object.ply")

        with self.assertRaises(self.rendering.AssetPathError) as traversal:
            self.rendering.resolve_asset_relative_path("../README.md")
        self.assertEqual(traversal.exception.status_code, 400)

        with self.assertRaises(self.rendering.AssetPathError) as unsupported:
            self.rendering.resolve_asset_relative_path("README.md")
        self.assertEqual(unsupported.exception.status_code, 404)

    def test_create_render_returns_public_asset_url_and_session(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            session_file = Path(tmp) / "3dgs_sessions.json"
            with (
                patch.object(self.rendering, "THREEDGS_SESSION_FILE", session_file),
                patch.object(self.rendering, "_now", return_value=1000.0),
            ):
                result = self.rendering.create_render("object.ply", quality="auto", ttl_sec=120)
                saved = json.loads(session_file.read_text(encoding="utf-8"))

        self.assertTrue(result["ok"])
        self.assertEqual(result["source"], "3dgs:mcp")
        self.assertEqual(result["ttl_sec"], 120)
        self.assertEqual(result["created_at"], 1000.0)
        self.assertEqual(result["expires_at"], 1120.0)
        self.assertIn(result["session_id"], self.rendering.sessions)
        self.assertIn(f"/viewer/sessions/{result['session_id']}?token=", result["render_url"])
        self.assertIn(f"/viewer/sessions/{result['session_id']}/assets/", result["asset"]["model_url"])
        self.assertIn("token=", result["asset"]["model_url"])

        saved_session = saved["sessions"][0]
        self.assertIn("viewer_token_hash", saved_session)
        self.assertNotIn(self._token_from_url(result["render_url"]), json.dumps(saved_session))

    def test_session_config_survives_memory_clear_when_session_file_exists(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            session_file = Path(tmp) / "3dgs_sessions.json"
            with (
                patch.object(self.rendering, "THREEDGS_SESSION_FILE", session_file),
                patch.object(self.rendering, "_now", return_value=1000.0),
            ):
                result = self.rendering.create_render("object.ply", quality="auto", ttl_sec=120)

            self.rendering.sessions.clear()

            with (
                patch.object(self.rendering, "THREEDGS_SESSION_FILE", session_file),
                patch.object(self.rendering, "_now", return_value=1001.0),
            ):
                restored = self.rendering.get_session_config(result["session_id"], self._token_from_url(result["render_url"]))

        self.assertEqual(restored["session_id"], result["session_id"])
        self.assertEqual(restored["asset"]["model_url"], result["asset"]["model_url"])

    def test_resolved_asset_must_be_in_splat_root(self) -> None:
        asset = {
            "path": BASE_DIR / "README.md",
        }

        with self.assertRaises(self.rendering.RenderCreateError):
            self.rendering.resolved_asset_path(asset)

    def test_expired_session_config_returns_410(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            session_file = Path(tmp) / "3dgs_sessions.json"
            with (
                patch.object(self.rendering, "THREEDGS_SESSION_FILE", session_file),
                patch.object(self.rendering, "_now", return_value=1000.0),
            ):
                result = self.rendering.create_render("object.ply", ttl_sec=1)

            with (
                patch.object(self.rendering, "THREEDGS_SESSION_FILE", session_file),
                patch.object(self.rendering, "_now", return_value=1002.0),
            ):
                with self.assertRaises(self.rendering.SessionExpiredError):
                    self.rendering.get_session_config(result["session_id"], self._token_from_url(result["render_url"]))

        self.assertNotIn(result["session_id"], self.rendering.sessions)

    def test_lookup_filename_rejects_absolute_and_parent_segments(self) -> None:
        with self.assertRaises(self.rendering.RenderCreateError):
            self.rendering.validate_lookup_filename("../object.ply")

        with self.assertRaises(self.rendering.RenderCreateError):
            self.rendering.validate_lookup_filename(str(Path("C:/tmp/object.ply")))

    def test_session_asset_path_requires_token_and_session_asset(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            session_file = Path(tmp) / "3dgs_sessions.json"
            with patch.object(self.rendering, "THREEDGS_SESSION_FILE", session_file):
                result = self.rendering.create_render("object.ply", ttl_sec=120)
                token = self._token_from_url(result["render_url"])
                relative_path = result["asset"]["relative_path"]

                resolved = self.rendering.resolve_session_asset_path(result["session_id"], relative_path, token)

                with self.assertRaises(self.rendering.SessionTokenError):
                    self.rendering.resolve_session_asset_path(result["session_id"], relative_path, "bad-token")

                with self.assertRaises(self.rendering.AssetPathError) as traversal:
                    self.rendering.resolve_session_asset_path(result["session_id"], "../README.md", token)

        self.assertEqual(resolved, self.rendering.resolve_asset_relative_path(relative_path))
        self.assertEqual(traversal.exception.status_code, 400)

    def test_session_asset_path_allows_rad_numeric_radc_chunk(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            session_file = Path(tmp) / "3dgs_sessions.json"
            with patch.object(self.rendering, "THREEDGS_SESSION_FILE", session_file):
                result = self.rendering.create_render("object.ply", quality="auto", ttl_sec=120)
                token = self._token_from_url(result["render_url"])
                relative_path = Path(result["asset"]["relative_path"])
                chunk_path = relative_path.with_name(f"{relative_path.stem}-0.radc")
                unrelated_chunk = relative_path.with_name(f"{relative_path.stem}x-0.radc")
                unrelated_path = self.rendering.SPLAT_DIR / unrelated_chunk

                self.assertEqual(relative_path.name, "object-balanced-lod.rad")
                self.assertTrue((self.rendering.SPLAT_DIR / chunk_path).exists())
                resolved = self.rendering.resolve_session_asset_path(
                    result["session_id"],
                    chunk_path.as_posix(),
                    token,
                )

                unrelated_path.write_bytes(b"radc")
                try:
                    with self.assertRaises(self.rendering.AssetPathError) as forbidden:
                        self.rendering.resolve_session_asset_path(
                            result["session_id"],
                            unrelated_chunk.as_posix(),
                            token,
                        )
                finally:
                    unrelated_path.unlink(missing_ok=True)

        self.assertEqual(resolved, self.rendering.resolve_asset_relative_path(chunk_path.as_posix()))
        self.assertEqual(forbidden.exception.status_code, 403)


class ThreeDGSMCPProtocolTests(unittest.TestCase):
    def setUp(self) -> None:
        server._MCP_SESSIONS.clear()
        self.client = TestClient(server.app)

    def _initialize(self) -> str:
        response = self.client.post(
            "/mcp",
            json={
                "jsonrpc": "2.0",
                "id": "init-1",
                "method": "initialize",
                "params": {"protocolVersion": "2025-06-18", "capabilities": {}},
            },
            headers={"Accept": "application/json, text/event-stream"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["result"]["protocolVersion"], "2025-06-18")
        session_id = response.headers.get("mcp-session-id")
        self.assertTrue(session_id)
        return str(session_id)

    def _initialized_headers(self) -> dict[str, str]:
        session_id = self._initialize()
        headers = {
            "Accept": "application/json, text/event-stream",
            "MCP-Protocol-Version": "2025-06-18",
            "Mcp-Session-Id": session_id,
        }
        response = self.client.post(
            "/mcp",
            json={"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}},
            headers=headers,
        )
        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.content, b"")
        return headers

    def test_get_mcp_returns_405(self) -> None:
        self.assertEqual(self.client.get("/mcp").status_code, 405)

    def test_initialize_returns_capabilities_and_session_header(self) -> None:
        session_id = self._initialize()
        self.assertIn(session_id, server._MCP_SESSIONS)

    def test_tools_call_requires_initialized_session(self) -> None:
        session_id = self._initialize()
        response = self.client.post(
            "/mcp",
            json={"jsonrpc": "2.0", "id": "call-1", "method": "tools/call", "params": {}},
            headers={"MCP-Protocol-Version": "2025-06-18", "Mcp-Session-Id": session_id},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["error"]["code"], -32002)

    def test_tools_list_shape_after_initialized(self) -> None:
        response = self.client.post(
            "/mcp",
            json={"jsonrpc": "2.0", "id": "list-1", "method": "tools/list", "params": {}},
            headers=self._initialized_headers(),
        )

        tool = response.json()["result"]["tools"][0]
        self.assertEqual(tool["name"], "3dgs.create_render")
        self.assertEqual(tool["inputSchema"]["properties"]["quality"]["enum"], ["auto", "preview", "balanced", "full", "source"])
        self.assertEqual(tool["inputSchema"]["properties"]["ttl_sec"]["minimum"], 1)
        self.assertIn("outputSchema", tool)

    def test_tools_call_returns_tool_result(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            session_file = Path(tmp) / "3dgs_sessions.json"
            with patch.object(server.rendering, "THREEDGS_SESSION_FILE", session_file):
                response = self.client.post(
                    "/mcp",
                    json={
                        "jsonrpc": "2.0",
                        "id": "call-1",
                        "method": "tools/call",
                        "params": {
                            "name": "3dgs.create_render",
                            "arguments": {"filename": "object.ply", "quality": "auto", "ttl_sec": 120},
                        },
                    },
                    headers=self._initialized_headers(),
                )

        result = response.json()["result"]
        self.assertFalse(result["isError"])
        self.assertTrue(result["structuredContent"]["ok"])
        self.assertIn("?token=", result["structuredContent"]["render_url"])
        self.assertEqual(json.loads(result["content"][0]["text"])["session_id"], result["structuredContent"]["session_id"])

    def test_tools_call_business_failure_is_tool_error(self) -> None:
        with patch.object(server.rendering, "resolve_splat_asset", return_value=None):
            response = self.client.post(
                "/mcp",
                json={
                    "jsonrpc": "2.0",
                    "id": "call-1",
                    "method": "tools/call",
                    "params": {
                        "name": "3dgs.create_render",
                        "arguments": {"filename": "missing-asset.ply", "quality": "auto"},
                    },
                },
                headers=self._initialized_headers(),
            )

        result = response.json()["result"]
        self.assertTrue(result["isError"])
        self.assertFalse(result["structuredContent"]["ok"])

    def test_mcp_endpoint_uses_bearer_auth_when_configured(self) -> None:
        payload = {
            "jsonrpc": "2.0",
            "id": "init-1",
            "method": "initialize",
            "params": {"protocolVersion": "2025-06-18"},
        }

        with patch.object(server, "THREEDGS_MCP_API_KEY", "secret"):
            unauthorized = self.client.post("/mcp", json=payload)
            authorized = self.client.post("/mcp", json=payload, headers={"Authorization": "Bearer secret"})

        self.assertEqual(unauthorized.status_code, 401)
        self.assertEqual(authorized.status_code, 200)


if __name__ == "__main__":
    unittest.main()
