from __future__ import annotations

import argparse
import re
import struct
from dataclasses import dataclass
from pathlib import Path


VERTEX_COUNT_RE = re.compile(rb"element vertex (\d+)\r?\n")
PLY_FLOAT_PROPS = (
    "x",
    "y",
    "z",
    "nx",
    "ny",
    "nz",
    "f_dc_0",
    "f_dc_1",
    "f_dc_2",
    "opacity",
    "scale_0",
    "scale_1",
    "scale_2",
    "rot_0",
    "rot_1",
    "rot_2",
    "rot_3",
)
ROW_STRUCT = struct.Struct("<17f")


@dataclass
class GaussianPly:
    path: Path
    header: bytes
    vertex_count: int
    rows: list[list[float]]


def _find_header_end(blob: bytes) -> int:
    marker = b"end_header"
    idx = blob.find(marker)
    if idx < 0:
        raise ValueError("Missing end_header")

    line_end = blob.find(b"\n", idx)
    if line_end < 0:
        raise ValueError("Malformed header terminator")
    return line_end + 1


def _normalize_header_line_endings(header: bytes) -> bytes:
    return header.replace(b"\r\n", b"\n")


def _parse_vertex_count(header: bytes) -> int:
    match = VERTEX_COUNT_RE.search(header)
    if not match:
        raise ValueError("Missing 'element vertex' declaration")
    return int(match.group(1))


def _validate_header(header: bytes) -> None:
    text = _normalize_header_line_endings(header).decode("ascii", errors="strict")
    lines = [line.strip() for line in text.splitlines()]

    if not lines or lines[0] != "ply":
        raise ValueError("Only PLY files are supported")
    if "format binary_little_endian 1.0" not in lines:
        raise ValueError("Only binary_little_endian PLY files are supported")
    if any(line.startswith("element face") for line in lines):
        raise ValueError("This script only supports Gaussian PLY files without faces")

    prop_lines = [line for line in lines if line.startswith("property ")]
    expected = [f"property float {name}" for name in PLY_FLOAT_PROPS]
    if prop_lines != expected:
        raise ValueError("Unexpected property layout; not a supported Gaussian PLY file")


def load_gaussian_ply(path: Path) -> GaussianPly:
    blob = path.read_bytes()
    header_end = _find_header_end(blob)
    header = blob[:header_end]
    body = blob[header_end:]

    _validate_header(header)
    vertex_count = _parse_vertex_count(header)
    expected_size = vertex_count * ROW_STRUCT.size
    if len(body) != expected_size:
        raise ValueError(
            f"{path} body size mismatch: expected {expected_size} bytes, got {len(body)} bytes"
        )

    rows: list[list[float]] = []
    for offset in range(0, len(body), ROW_STRUCT.size):
        rows.append(list(ROW_STRUCT.unpack_from(body, offset)))

    return GaussianPly(path=path, header=header, vertex_count=vertex_count, rows=rows)


def apply_translation(rows: list[list[float]], dx: float, dy: float, dz: float) -> None:
    if dx == 0.0 and dy == 0.0 and dz == 0.0:
        return

    for row in rows:
        row[0] += dx
        row[1] += dy
        row[2] += dz


def build_output_header(header: bytes, vertex_count: int) -> bytes:
    normalized = _normalize_header_line_endings(header)
    return VERTEX_COUNT_RE.sub(
        f"element vertex {vertex_count}\\n".encode("ascii"),
        normalized,
        count=1,
    )


def write_gaussian_ply(path: Path, header: bytes, rows: list[list[float]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as fh:
        fh.write(header)
        for row in rows:
            fh.write(ROW_STRUCT.pack(*row))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Merge binary Gaussian PLY files by concatenating vertex records."
    )
    parser.add_argument("inputs", nargs="+", help="Input Gaussian PLY files")
    parser.add_argument("--output", required=True, help="Output merged PLY path")
    parser.add_argument(
        "--translate",
        nargs=4,
        action="append",
        metavar=("INDEX", "DX", "DY", "DZ"),
        help="Translate one input file before merging. INDEX is 1-based.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    input_paths = [Path(item).resolve() for item in args.inputs]
    output_path = Path(args.output).resolve()

    models = [load_gaussian_ply(path) for path in input_paths]
    translations: dict[int, tuple[float, float, float]] = {}

    for item in args.translate or []:
        index = int(item[0])
        if not 1 <= index <= len(models):
            raise ValueError(f"Translation index out of range: {index}")
        translations[index - 1] = (float(item[1]), float(item[2]), float(item[3]))

    merged_rows: list[list[float]] = []
    for idx, model in enumerate(models):
        dx, dy, dz = translations.get(idx, (0.0, 0.0, 0.0))
        apply_translation(model.rows, dx, dy, dz)
        merged_rows.extend(model.rows)

    output_header = build_output_header(models[0].header, len(merged_rows))
    write_gaussian_ply(output_path, output_header, merged_rows)

    print(f"Merged {len(models)} files into: {output_path}")
    print(f"Total vertices: {len(merged_rows)}")
    for idx, model in enumerate(models, start=1):
        dx, dy, dz = translations.get(idx - 1, (0.0, 0.0, 0.0))
        print(f"{idx}. {model.path.name} vertices={model.vertex_count} translate=({dx}, {dy}, {dz})")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
