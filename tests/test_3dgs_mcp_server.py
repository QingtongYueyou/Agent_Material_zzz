from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from config.settings import BASE_DIR


class ThreeDGSRenderingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        from mcp_3dgs import rendering

        cls.rendering = rendering

    def setUp(self) -> None:
        self.rendering.sessions.clear()

    def tearDown(self) -> None:
        self.rendering.sessions.clear()

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

        self.assertTrue(result["ok"])
        self.assertEqual(result["source"], "3dgs:mcp")
        self.assertEqual(result["ttl_sec"], 120)
        self.assertEqual(result["created_at"], 1000.0)
        self.assertEqual(result["expires_at"], 1120.0)
        self.assertIn(result["session_id"], self.rendering.sessions)
        self.assertTrue(result["render_url"].endswith(f"/viewer/sessions/{result['session_id']}"))
        self.assertTrue(result["asset"]["model_url"].startswith("http://127.0.0.1:8090/assets/"))

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
                restored = self.rendering.get_session_config(result["session_id"])

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
                    self.rendering.get_session_config(result["session_id"])

        self.assertNotIn(result["session_id"], self.rendering.sessions)

    def test_lookup_filename_rejects_absolute_and_parent_segments(self) -> None:
        with self.assertRaises(self.rendering.RenderCreateError):
            self.rendering.validate_lookup_filename("../object.ply")

        with self.assertRaises(self.rendering.RenderCreateError):
            self.rendering.validate_lookup_filename(str(Path("C:/tmp/object.ply")))


if __name__ == "__main__":
    unittest.main()
