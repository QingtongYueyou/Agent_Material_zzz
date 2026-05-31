from __future__ import annotations

import math
import os
import struct
import tempfile
import unittest
from pathlib import Path

from core.perf_metrics import get_ply_bounds as legacy_get_ply_bounds
from core.ply_utils import get_ply_bounds, get_ply_vertex_count, read_ply_header


class PlyUtilsTests(unittest.TestCase):
    def test_vertex_count_and_header_for_ascii_ply(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "points.ply"
            path.write_text(
                "\n".join(
                    [
                        "ply",
                        "format ascii 1.0",
                        "element vertex 2",
                        "property float x",
                        "property float y",
                        "property float z",
                        "end_header",
                        "0 0 0",
                        "1 1 1",
                    ]
                ),
                encoding="ascii",
            )

            self.assertEqual(get_ply_vertex_count(path), 2)
            self.assertEqual(read_ply_header(path)[2], "element vertex 2")

    def test_binary_little_endian_bounds(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            asset_dir = Path(tmp) / "assets"
            asset_dir.mkdir()
            path = asset_dir / "cloud.ply"
            header = (
                "ply\n"
                "format binary_little_endian 1.0\n"
                "element vertex 3\n"
                "property float x\n"
                "property float y\n"
                "property float z\n"
                "end_header\n"
            ).encode("ascii")
            points = [(-1.0, 2.0, 0.5), (3.0, -2.0, 4.5), (1.0, 0.0, -3.5)]
            payload = b"".join(struct.pack("<fff", *point) for point in points)
            path.write_bytes(header + payload)

            bounds = get_ply_bounds(path)

            self.assertIsNotNone(bounds)
            assert bounds is not None
            self.assertEqual(bounds["vertex_count"], 3)
            self.assertEqual(bounds["min"], [-1.0, -2.0, -3.5])
            self.assertEqual(bounds["max"], [3.0, 2.0, 4.5])
            self.assertEqual(bounds["center"], [1.0, 0.0, 0.5])
            self.assertTrue(math.isclose(bounds["radius"], math.sqrt(24.0)))
            self.assertEqual(legacy_get_ply_bounds(path)["min"], bounds["min"])

    def test_bounds_rejects_ascii_ply(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "points.ply"
            path.write_text(
                "ply\nformat ascii 1.0\nelement vertex 1\n"
                "property float x\nproperty float y\nproperty float z\nend_header\n0 0 0\n",
                encoding="ascii",
            )

            self.assertIsNone(get_ply_bounds(path))

    def test_bounds_returns_none_for_truncated_binary_payload(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            asset_dir = Path(tmp) / "assets"
            asset_dir.mkdir()
            path = asset_dir / "truncated.ply"
            header = (
                "ply\n"
                "format binary_little_endian 1.0\n"
                "element vertex 1\n"
                "property float x\n"
                "property float y\n"
                "property float z\n"
                "end_header\n"
            ).encode("ascii")
            path.write_bytes(header + b"\x00")

            self.assertIsNone(get_ply_bounds(path))

    def test_binary_little_endian_int_coordinate_bounds(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            asset_dir = Path(tmp) / "assets"
            asset_dir.mkdir()
            path = asset_dir / "ints.ply"
            header = (
                "ply\n"
                "format binary_little_endian 1.0\n"
                "element vertex 2\n"
                "property int x\n"
                "property int y\n"
                "property int z\n"
                "end_header\n"
            ).encode("ascii")
            points = [(-5, 2, 9), (7, -3, 4)]
            payload = b"".join(struct.pack("<iii", *point) for point in points)
            path.write_bytes(header + payload)

            bounds = get_ply_bounds(path)

            self.assertIsNotNone(bounds)
            assert bounds is not None
            self.assertEqual(bounds["min"], [-5, -3, 4])
            self.assertEqual(bounds["max"], [7, 2, 9])
            self.assertEqual(bounds["center"], [1.0, -0.5, 6.5])

    def test_bounds_cache_does_not_reuse_same_stem_from_different_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            first_dir = root / "first"
            second_dir = root / "second"
            first_dir.mkdir()
            second_dir.mkdir()
            first_path = first_dir / "cloud.ply"
            second_path = second_dir / "cloud.ply"
            header = (
                "ply\n"
                "format binary_little_endian 1.0\n"
                "element vertex 1\n"
                "property float x\n"
                "property float y\n"
                "property float z\n"
                "end_header\n"
            ).encode("ascii")
            first_path.write_bytes(header + struct.pack("<fff", 1.0, 2.0, 3.0))
            second_path.write_bytes(header + struct.pack("<fff", -4.0, -5.0, -6.0))
            same_mtime = 1_700_000_000
            os.utime(first_path, (same_mtime, same_mtime))
            os.utime(second_path, (same_mtime, same_mtime))

            first_bounds = get_ply_bounds(first_path)
            second_bounds = get_ply_bounds(second_path)

            self.assertIsNotNone(first_bounds)
            self.assertIsNotNone(second_bounds)
            assert first_bounds is not None
            assert second_bounds is not None
            self.assertEqual(first_bounds["min"], [1.0, 2.0, 3.0])
            self.assertEqual(second_bounds["min"], [-4.0, -5.0, -6.0])


if __name__ == "__main__":
    unittest.main()
