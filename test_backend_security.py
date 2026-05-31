from __future__ import annotations

import unittest

from config.settings import CIF_DIR, STATIC_DIR, _build_cors_allowed_origins


class CorsConfigTests(unittest.TestCase):
    def test_production_cors_does_not_keep_wildcard(self) -> None:
        origins = _build_cors_allowed_origins("production", "*,https://example.com")

        self.assertEqual(origins, ["https://example.com"])

    def test_production_cors_requires_explicit_non_wildcard_origin(self) -> None:
        with self.assertRaises(RuntimeError):
            _build_cors_allowed_origins("production", None)

        with self.assertRaises(RuntimeError):
            _build_cors_allowed_origins("production", "*")

    def test_development_cors_has_localhost_defaults(self) -> None:
        origins = _build_cors_allowed_origins("development", None)

        self.assertIn("http://localhost:5173", origins)


class PathResolutionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        try:
            from fastapi import HTTPException
            from api.main import _resolve_asset_file, _resolve_cif_path
        except ImportError as exc:
            raise unittest.SkipTest(f"API dependencies are unavailable: {exc}") from exc

        cls.http_exception = HTTPException
        cls.resolve_asset_file = staticmethod(_resolve_asset_file)
        cls.resolve_cif_path = staticmethod(_resolve_cif_path)

    def setUp(self) -> None:
        self.cif_file = CIF_DIR / "test_backend_security.cif"
        self.asset_file = STATIC_DIR / "test_backend_security.radc"
        self.cif_file.write_text("data_test\n", encoding="utf-8")
        self.asset_file.write_bytes(b"radc")

    def tearDown(self) -> None:
        for path in (self.cif_file, self.asset_file):
            try:
                path.unlink()
            except FileNotFoundError:
                pass

    def test_cif_path_must_be_cif_file_in_cif_dir(self) -> None:
        self.assertEqual(self.resolve_cif_path(self.cif_file.name), self.cif_file.resolve())

        with self.assertRaises(self.http_exception) as readme:
            self.resolve_cif_path("README.md")
        self.assertEqual(readme.exception.status_code, 400)

        with self.assertRaises(self.http_exception) as traversal:
            self.resolve_cif_path("../cif_files/test_backend_security.cif")
        self.assertEqual(traversal.exception.status_code, 400)

    def test_asset_path_must_stay_in_static_assets(self) -> None:
        relative_asset = self.asset_file.relative_to(STATIC_DIR.parent).as_posix()
        self.assertEqual(self.resolve_asset_file(relative_asset), self.asset_file.resolve())

        with self.assertRaises(self.http_exception) as outside_static:
            self.resolve_asset_file("cif_files/test_backend_security.cif")
        self.assertEqual(outside_static.exception.status_code, 400)


if __name__ == "__main__":
    unittest.main()
