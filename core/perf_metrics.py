from __future__ import annotations

import csv
import json
import math
import struct
from datetime import datetime, timezone
from pathlib import Path

from config.settings import INTERACTION_METRICS_FILE, RENDER_METRICS_FILE


RENDER_METRIC_FIELDS = [
    "timestamp_utc",
    "event_type",
    "model_name",
    "model_format",
    "vertex_count",
    "file_size_bytes",
    "click_to_request_start_ms",
    "request_start_to_scene_ready_ms",
    "scene_ready_to_first_frame_ms",
    "click_to_first_frame_ms",
    "viewport_width",
    "viewport_height",
    "user_agent",
]

INTERACTION_METRIC_FIELDS = [
    "timestamp_utc",
    "event_type",
    "model_name",
    "model_format",
    "vertex_count",
    "file_size_bytes",
    "interaction_type",
    "input_to_camera_change_ms",
    "viewport_width",
    "viewport_height",
    "user_agent",
]


def get_ply_vertex_count(path: str | Path) -> int | None:
    file_path = Path(path)
    if file_path.suffix.lower() != ".ply" or not file_path.exists():
        return None

    with file_path.open("rb") as fh:
        for raw_line in fh:
            try:
                line = raw_line.decode("ascii", errors="ignore").strip()
            except Exception:
                return None

            if line.startswith("element vertex "):
                value = line.split()[-1]
                try:
                    return int(value)
                except ValueError:
                    return None

            if line == "end_header":
                break

    return None


_PLY_SCALAR_SIZES = {
    "char": 1,
    "uchar": 1,
    "int8": 1,
    "uint8": 1,
    "short": 2,
    "ushort": 2,
    "int16": 2,
    "uint16": 2,
    "int": 4,
    "uint": 4,
    "int32": 4,
    "uint32": 4,
    "float": 4,
    "float32": 4,
    "double": 8,
    "float64": 8,
}


def _read_ply_header(path: Path) -> tuple[list[str], int] | None:
    header_lines: list[str] = []
    header_size = 0
    with path.open("rb") as fh:
        for raw_line in fh:
            header_size += len(raw_line)
            try:
                line = raw_line.decode("ascii", errors="strict").strip()
            except UnicodeDecodeError:
                return None
            header_lines.append(line)
            if line == "end_header":
                return header_lines, header_size
    return None


def get_ply_bounds(path: str | Path) -> dict[str, object] | None:
    file_path = Path(path)
    if file_path.suffix.lower() != ".ply" or not file_path.exists():
        return None

    cache_dir = file_path.parent.parent / "_bounds"
    cache_path = cache_dir / f"{file_path.stem}.bounds.json"
    stat = file_path.stat()
    if cache_path.exists():
        try:
            cached = json.loads(cache_path.read_text(encoding="utf-8"))
            if (
                int(cached.get("source_mtime", -1)) == int(stat.st_mtime)
                and int(cached.get("source_size", -1)) == int(stat.st_size)
            ):
                return cached
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            pass

    header = _read_ply_header(file_path)
    if header is None:
        return None

    header_lines, header_size = header
    if "format binary_little_endian 1.0" not in header_lines:
        return None

    vertex_count: int | None = None
    vertex_properties: list[tuple[str, str]] = []
    in_vertex = False
    for line in header_lines:
        parts = line.split()
        if len(parts) >= 3 and parts[0] == "element":
            in_vertex = parts[1] == "vertex"
            if in_vertex:
                try:
                    vertex_count = int(parts[2])
                except ValueError:
                    return None
            continue
        if in_vertex and len(parts) == 3 and parts[0] == "property":
            vertex_properties.append((parts[2], parts[1]))
        elif in_vertex and line.startswith("property list "):
            return None

    if vertex_count is None or vertex_count <= 0:
        return None

    offsets: dict[str, tuple[int, str]] = {}
    stride = 0
    for name, scalar_type in vertex_properties:
        size = _PLY_SCALAR_SIZES.get(scalar_type)
        if size is None:
            return None
        if name in {"x", "y", "z"}:
            offsets[name] = (stride, scalar_type)
        stride += size

    if not {"x", "y", "z"}.issubset(offsets) or stride <= 0:
        return None

    unpackers = {}
    for axis in ("x", "y", "z"):
        offset, scalar_type = offsets[axis]
        fmt = "<f" if scalar_type in {"float", "float32"} else "<d"
        unpackers[axis] = (offset, struct.Struct(fmt))

    min_x = min_y = min_z = math.inf
    max_x = max_y = max_z = -math.inf
    chunk_records = 65536
    chunk_size = stride * chunk_records
    seen = 0

    with file_path.open("rb") as fh:
        fh.seek(header_size)
        carry = b""
        while seen < vertex_count:
            raw = carry + fh.read(chunk_size)
            if not raw:
                break
            usable = min(len(raw) // stride, vertex_count - seen)
            limit = usable * stride
            for base in range(0, limit, stride):
                x = unpackers["x"][1].unpack_from(raw, base + unpackers["x"][0])[0]
                y = unpackers["y"][1].unpack_from(raw, base + unpackers["y"][0])[0]
                z = unpackers["z"][1].unpack_from(raw, base + unpackers["z"][0])[0]
                min_x = min(min_x, x)
                min_y = min(min_y, y)
                min_z = min(min_z, z)
                max_x = max(max_x, x)
                max_y = max(max_y, y)
                max_z = max(max_z, z)
            seen += usable
            carry = raw[limit:]

    if seen <= 0 or not all(math.isfinite(v) for v in [min_x, min_y, min_z, max_x, max_y, max_z]):
        return None

    center = [(min_x + max_x) / 2, (min_y + max_y) / 2, (min_z + max_z) / 2]
    radius = math.sqrt(
        ((max_x - min_x) / 2) ** 2
        + ((max_y - min_y) / 2) ** 2
        + ((max_z - min_z) / 2) ** 2
    )
    result: dict[str, object] = {
        "source_mtime": int(stat.st_mtime),
        "source_size": int(stat.st_size),
        "vertex_count": int(vertex_count),
        "center": center,
        "radius": radius,
        "min": [min_x, min_y, min_z],
        "max": [max_x, max_y, max_z],
    }

    try:
        cache_dir.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass

    return result


def append_render_metric(record: dict[str, object]) -> None:
    RENDER_METRICS_FILE.parent.mkdir(parents=True, exist_ok=True)
    file_exists = RENDER_METRICS_FILE.exists()

    row = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "event_type": record.get("event_type", ""),
        "model_name": record.get("model_name", ""),
        "model_format": record.get("model_format", ""),
        "vertex_count": record.get("vertex_count", ""),
        "file_size_bytes": record.get("file_size_bytes", ""),
        "click_to_request_start_ms": record.get("click_to_request_start_ms", ""),
        "request_start_to_scene_ready_ms": record.get("request_start_to_scene_ready_ms", ""),
        "scene_ready_to_first_frame_ms": record.get("scene_ready_to_first_frame_ms", ""),
        "click_to_first_frame_ms": record.get("click_to_first_frame_ms", ""),
        "viewport_width": record.get("viewport_width", ""),
        "viewport_height": record.get("viewport_height", ""),
        "user_agent": record.get("user_agent", ""),
    }

    with RENDER_METRICS_FILE.open("a", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=RENDER_METRIC_FIELDS)
        if not file_exists:
            writer.writeheader()
        writer.writerow(row)


def append_interaction_metric(record: dict[str, object]) -> None:
    INTERACTION_METRICS_FILE.parent.mkdir(parents=True, exist_ok=True)
    file_exists = INTERACTION_METRICS_FILE.exists()

    row = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "event_type": record.get("event_type", ""),
        "model_name": record.get("model_name", ""),
        "model_format": record.get("model_format", ""),
        "vertex_count": record.get("vertex_count", ""),
        "file_size_bytes": record.get("file_size_bytes", ""),
        "interaction_type": record.get("interaction_type", ""),
        "input_to_camera_change_ms": record.get("input_to_camera_change_ms", ""),
        "viewport_width": record.get("viewport_width", ""),
        "viewport_height": record.get("viewport_height", ""),
        "user_agent": record.get("user_agent", ""),
    }

    with INTERACTION_METRICS_FILE.open("a", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=INTERACTION_METRIC_FIELDS)
        if not file_exists:
            writer.writeheader()
        writer.writerow(row)
