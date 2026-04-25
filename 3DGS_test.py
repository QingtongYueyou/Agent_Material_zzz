from __future__ import annotations

import argparse
import math
import struct
from pathlib import Path

import numpy as np


DEFAULT_INPUT = Path(r"D:\清瞳月由\硕士\材料可视化\材料数据\10000\3D10000_35a.vtk")
DEFAULT_OUTPUT = Path(r"D:\wyfzzz\PyCharm\MyProjects\Agent_Material\mytest\Agent\static\splat_files\3D10000_35a_interface.ply")
DEFAULT_POINT_OUTPUT = Path(r"D:\wyfzzz\PyCharm\MyProjects\Agent_Material\mytest\Agent\static\splat_files\3D10000_35a_interface_points.ply")

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
SH_C0 = 0.28209479177387814
PALETTE = np.array(
    [
        [231, 76, 60],
        [52, 152, 219],
        [46, 204, 113],
        [241, 196, 15],
        [155, 89, 182],
        [26, 188, 156],
        [230, 126, 34],
        [149, 165, 166],
    ],
    dtype=np.float32,
) / 255.0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Extract interface voxels from a 4-column phase-field text grid and write a Gaussian PLY."
    )
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT, help="Input 4-column text file.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="Output Gaussian PLY path.")
    parser.add_argument(
        "--point-output",
        type=Path,
        default=DEFAULT_POINT_OUTPUT,
        help="Output standard point-cloud PLY path.",
    )
    parser.add_argument(
        "--format",
        choices=("gaussian", "points"),
        default="gaussian",
        help="Choose Gaussian PLY or standard RGB point-cloud PLY output.",
    )
    parser.add_argument(
        "--phase",
        type=int,
        action="append",
        default=[],
        help="Keep only interface voxels whose phase value matches one of these values. Repeatable.",
    )
    parser.add_argument(
        "--sample-step",
        type=int,
        default=2,
        help="Subsample interface voxels by taking every Nth point after extraction.",
    )
    parser.add_argument(
        "--alpha",
        type=float,
        default=0.85,
        help="Target alpha in [0, 1) for each Gaussian.",
    )
    parser.add_argument(
        "--voxel-scale",
        type=float,
        default=0.55,
        help="Base world-space Gaussian radius before log conversion.",
    )
    parser.add_argument(
        "--sparse-mode",
        choices=("error", "as-points"),
        default="error",
        help="How to handle non-dense grids. Use as-points to convert rows directly without interface extraction.",
    )
    return parser.parse_args()


def load_phase_grid(path: Path) -> tuple[np.ndarray, tuple[int, int, int], tuple[int, int, int]]:
    data = np.loadtxt(path, dtype=np.int32)
    if data.ndim != 2 or data.shape[1] != 4:
        raise ValueError(f"Expected a 4-column text grid, got shape {data.shape}")

    coords = data[:, :3]
    values = data[:, 3]

    mins = coords.min(axis=0)
    maxs = coords.max(axis=0)
    dims = tuple((maxs - mins + 1).tolist())
    expected = int(np.prod(dims))
    if expected != len(values):
        raise ValueError(
            f"Grid is not dense/rectangular: expected {expected} voxels from bounds, got {len(values)} rows"
        )

    grid = np.empty(dims, dtype=np.int32)
    shifted = coords - mins
    grid[shifted[:, 0], shifted[:, 1], shifted[:, 2]] = values
    return grid, tuple(int(x) for x in mins), tuple(int(x) for x in maxs)


def load_phase_points(path: Path) -> tuple[np.ndarray, np.ndarray, tuple[int, int, int], tuple[int, int, int]]:
    data = np.loadtxt(path, dtype=np.int32)
    if data.ndim != 2 or data.shape[1] != 4:
        raise ValueError(f"Expected a 4-column text grid, got shape {data.shape}")

    coords = data[:, :3]
    values = data[:, 3]
    mins = coords.min(axis=0)
    maxs = coords.max(axis=0)
    return coords, values, tuple(int(x) for x in mins), tuple(int(x) for x in maxs)


def compute_interface_mask(grid: np.ndarray) -> np.ndarray:
    mask = np.zeros_like(grid, dtype=bool)

    diff_x = grid[1:, :, :] != grid[:-1, :, :]
    mask[1:, :, :] |= diff_x
    mask[:-1, :, :] |= diff_x

    diff_y = grid[:, 1:, :] != grid[:, :-1, :]
    mask[:, 1:, :] |= diff_y
    mask[:, :-1, :] |= diff_y

    diff_z = grid[:, :, 1:] != grid[:, :, :-1]
    mask[:, :, 1:] |= diff_z
    mask[:, :, :-1] |= diff_z

    return mask


def logit(alpha: float) -> float:
    alpha = min(max(alpha, 1e-4), 1.0 - 1e-4)
    return math.log(alpha / (1.0 - alpha))


def rgb_to_sh_dc(rgb: np.ndarray) -> np.ndarray:
    return (rgb - 0.5) / SH_C0


def label_to_rgb(label: int) -> np.ndarray:
    return PALETTE[label % len(PALETTE)]


def build_gaussian_rows(
    grid: np.ndarray,
    interface_mask: np.ndarray,
    origin: tuple[int, int, int],
    selected_phases: set[int],
    sample_step: int,
    alpha: float,
    voxel_scale: float,
) -> list[list[float]]:
    coords = np.argwhere(interface_mask)
    if selected_phases:
        labels = grid[coords[:, 0], coords[:, 1], coords[:, 2]]
        coords = coords[np.isin(labels, list(selected_phases))]

    step = max(sample_step, 1)
    if step > 1 and len(coords) > 0:
        coords = coords[::step]

    rows: list[list[float]] = []
    opacity_raw = logit(alpha)
    scale_raw = math.log(max(voxel_scale, 1e-4))

    ox, oy, oz = origin
    for i, j, k in coords:
        label = int(grid[i, j, k])
        rgb = label_to_rgb(label)
        sh = rgb_to_sh_dc(rgb)

        rows.append(
            [
                float(ox + i),
                float(oy + j),
                float(oz + k),
                0.0,
                0.0,
                1.0,
                float(sh[0]),
                float(sh[1]),
                float(sh[2]),
                float(opacity_raw),
                float(scale_raw),
                float(scale_raw),
                float(scale_raw),
                1.0,
                0.0,
                0.0,
                0.0,
            ]
        )

    return rows


def build_gaussian_rows_from_points(
    coords: np.ndarray,
    labels: np.ndarray,
    selected_phases: set[int],
    sample_step: int,
    alpha: float,
    voxel_scale: float,
) -> list[list[float]]:
    if selected_phases:
        keep = np.isin(labels, list(selected_phases))
        coords = coords[keep]
        labels = labels[keep]

    step = max(sample_step, 1)
    if step > 1 and len(coords) > 0:
        coords = coords[::step]
        labels = labels[::step]

    rows: list[list[float]] = []
    opacity_raw = logit(alpha)
    scale_raw = math.log(max(voxel_scale, 1e-4))

    for (x, y, z), label_value in zip(coords, labels):
        label = int(label_value)
        rgb = label_to_rgb(label)
        sh = rgb_to_sh_dc(rgb)
        rows.append(
            [
                float(x),
                float(y),
                float(z),
                0.0,
                0.0,
                1.0,
                float(sh[0]),
                float(sh[1]),
                float(sh[2]),
                float(opacity_raw),
                float(scale_raw),
                float(scale_raw),
                float(scale_raw),
                1.0,
                0.0,
                0.0,
                0.0,
            ]
        )

    return rows


def build_ply_header(vertex_count: int) -> bytes:
    lines = [
        "ply",
        "format binary_little_endian 1.0",
        f"element vertex {vertex_count}",
        *[f"property float {name}" for name in PLY_FLOAT_PROPS],
        "end_header",
    ]
    return ("\n".join(lines) + "\n").encode("ascii")


def write_gaussian_ply(path: Path, rows: list[list[float]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    header = build_ply_header(len(rows))
    with path.open("wb") as fh:
        fh.write(header)
        for row in rows:
            fh.write(ROW_STRUCT.pack(*row))


def build_point_rows(
    grid: np.ndarray,
    interface_mask: np.ndarray,
    origin: tuple[int, int, int],
    selected_phases: set[int],
    sample_step: int,
) -> list[tuple[float, float, float, int, int, int]]:
    coords = np.argwhere(interface_mask)
    if selected_phases:
        labels = grid[coords[:, 0], coords[:, 1], coords[:, 2]]
        coords = coords[np.isin(labels, list(selected_phases))]

    step = max(sample_step, 1)
    if step > 1 and len(coords) > 0:
        coords = coords[::step]

    ox, oy, oz = origin
    rows: list[tuple[float, float, float, int, int, int]] = []
    for i, j, k in coords:
        label = int(grid[i, j, k])
        rgb = np.clip(label_to_rgb(label) * 255.0, 0, 255).astype(np.uint8)
        rows.append(
            (
                float(ox + i),
                float(oy + j),
                float(oz + k),
                int(rgb[0]),
                int(rgb[1]),
                int(rgb[2]),
            )
        )
    return rows


def build_point_ply_header(vertex_count: int) -> bytes:
    lines = [
        "ply",
        "format binary_little_endian 1.0",
        f"element vertex {vertex_count}",
        "property float x",
        "property float y",
        "property float z",
        "property uchar red",
        "property uchar green",
        "property uchar blue",
        "end_header",
    ]
    return ("\n".join(lines) + "\n").encode("ascii")


def write_point_ply(path: Path, rows: list[tuple[float, float, float, int, int, int]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    header = build_point_ply_header(len(rows))
    point_struct = struct.Struct("<fffBBB")
    with path.open("wb") as fh:
        fh.write(header)
        for row in rows:
            fh.write(point_struct.pack(*row))


def main() -> int:
    args = parse_args()
    print(f"Loading grid from: {args.input}")
    try:
        grid, mins, maxs = load_phase_grid(args.input)
    except ValueError:
        if args.sparse_mode != "as-points":
            raise
        coords, labels, mins, maxs = load_phase_points(args.input)
        print(f"Sparse point table: {len(labels)} rows, bounds: min={mins}, max={maxs}")
        if args.format != "gaussian":
            raise ValueError("--sparse-mode as-points currently supports --format gaussian only")
        rows = build_gaussian_rows_from_points(
            coords=coords,
            labels=labels,
            selected_phases=set(args.phase),
            sample_step=args.sample_step,
            alpha=args.alpha,
            voxel_scale=args.voxel_scale,
        )
        print(f"Gaussians to write: {len(rows)}")
        write_gaussian_ply(args.output, rows)
        print(f"Wrote Gaussian PLY: {args.output}")
        return 0
    print(f"Grid shape: {grid.shape}, bounds: min={mins}, max={maxs}")

    interface_mask = compute_interface_mask(grid)
    interface_count = int(interface_mask.sum())
    print(f"Interface voxels before filtering: {interface_count}")

    if args.format == "gaussian":
        rows = build_gaussian_rows(
            grid=grid,
            interface_mask=interface_mask,
            origin=mins,
            selected_phases=set(args.phase),
            sample_step=args.sample_step,
            alpha=args.alpha,
            voxel_scale=args.voxel_scale,
        )
        print(f"Gaussians to write: {len(rows)}")
        write_gaussian_ply(args.output, rows)
        print(f"Wrote Gaussian PLY: {args.output}")
    else:
        rows = build_point_rows(
            grid=grid,
            interface_mask=interface_mask,
            origin=mins,
            selected_phases=set(args.phase),
            sample_step=args.sample_step,
        )
        print(f"Points to write: {len(rows)}")
        write_point_ply(args.point_output, rows)
        print(f"Wrote standard point-cloud PLY: {args.point_output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
