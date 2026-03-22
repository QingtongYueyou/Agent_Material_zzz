from __future__ import annotations

import csv
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
