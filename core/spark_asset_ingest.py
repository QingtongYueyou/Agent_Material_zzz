from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any

from config.settings import (
    BASE_DIR,
    SPARK_AUTO_INGEST,
    SPARK_AUTO_VARIANT,
    SPARK_ROOT,
    SPLAT_DERIVED_DIR,
    SPLAT_PIPELINE_DIR,
    SPLAT_SOURCE_DIR,
    SPARK_STATUS_FILE,
    SPLAT_DIR,
)


RAW_SOURCE_SUFFIXES = {".ply", ".spz", ".splat", ".ksplat"}
BUILDABLE_SOURCE_SUFFIXES = {".ply", ".spz"}
_PROCESS_LOCK = threading.Lock()
_ACTIVE_PROCESS: subprocess.Popen[str] | None = None
_LAST_LAUNCH_MONO = 0.0
_MIN_RELAUNCH_INTERVAL_SEC = 5.0


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None

    if isinstance(data, dict):
        return data
    return None


def _is_source_candidate(path: Path) -> bool:
    if not path.is_file():
        return False

    if path.suffix.lower() not in RAW_SOURCE_SUFFIXES:
        return False

    return not path.stem.lower().endswith("-lod")


def _iter_source_candidates() -> list[Path]:
    candidates = set(path.resolve() for path in SPLAT_SOURCE_DIR.iterdir() if _is_source_candidate(path))
    candidates.update(path.resolve() for path in SPLAT_DIR.iterdir() if _is_source_candidate(path))
    return sorted(Path(path) for path in candidates)


def _manifest_path_for_asset(asset_id: str) -> Path:
    return SPLAT_DERIVED_DIR / asset_id / f"{asset_id}.manifest.json"


def _resolve_manifest_variant_path(manifest_path: Path, variant_name: str) -> Path | None:
    manifest = _read_json(manifest_path)
    if not manifest:
        return None

    variants = manifest.get("variants")
    if not isinstance(variants, dict):
        return None

    payload = variants.get(variant_name)
    if not isinstance(payload, dict):
        return None

    raw_path = payload.get("path") or payload.get("file") or payload.get("relative_path")
    if not isinstance(raw_path, str) or not raw_path.strip():
        return None

    candidate = Path(raw_path)
    if candidate.is_absolute():
        return candidate if candidate.exists() else None

    splat_dir = manifest_path.parent.parent.parent if manifest_path.parent.parent.parent.exists() else SPLAT_DIR
    search_roots = [
        manifest_path.parent,
        SPLAT_SOURCE_DIR,
        SPLAT_DERIVED_DIR,
        splat_dir,
    ]
    seen: set[Path] = set()
    for root in search_roots:
        resolved = (root / candidate).resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        if resolved.exists():
            return resolved
    return None


def _variant_is_current(source_path: Path, variant_name: str) -> bool:
    manifest_path = _manifest_path_for_asset(source_path.stem)
    if not manifest_path.exists():
        return False

    variant_path = _resolve_manifest_variant_path(manifest_path, variant_name)
    if variant_path is None:
        return False

    manifest = _read_json(manifest_path) or {}
    if str(manifest.get("default_variant") or "").strip() != variant_name:
        return False

    try:
        return source_path.stat().st_mtime <= variant_path.stat().st_mtime
    except OSError:
        return False


def _source_variant_matches(source_path: Path) -> bool:
    manifest_path = _manifest_path_for_asset(source_path.stem)
    if not manifest_path.exists():
        return False

    variant_path = _resolve_manifest_variant_path(manifest_path, "source")
    if variant_path is None:
        return False

    try:
        return variant_path.resolve() == source_path.resolve()
    except OSError:
        return False


def _collect_pending_assets() -> list[dict[str, Any]]:
    status_data = _read_json(SPARK_STATUS_FILE) or {}
    status_assets = status_data.get("assets")
    if not isinstance(status_assets, dict):
        status_assets = {}

    pending: list[dict[str, Any]] = []
    for source_path in _iter_source_candidates():
        buildable = source_path.suffix.lower() in BUILDABLE_SOURCE_SUFFIXES
        source_mtime = int(source_path.stat().st_mtime)
        last_status = status_assets.get(source_path.stem)
        if (
            buildable
            and isinstance(last_status, dict)
            and str(last_status.get("state") or "") == "error"
            and str(last_status.get("variant") or "") == SPARK_AUTO_VARIANT
            and int(last_status.get("source_mtime") or -1) == source_mtime
        ):
            continue

        needs_source_registration = not _source_variant_matches(source_path)
        needs_variant_build = buildable and SPARK_ROOT.exists() and not _variant_is_current(
            source_path,
            SPARK_AUTO_VARIANT,
        )

        reason = ""
        if needs_variant_build:
            reason = f"missing_or_stale_{SPARK_AUTO_VARIANT}"
        elif needs_source_registration:
            reason = "missing_source_variant"

        if not reason:
            continue

        pending.append(
            {
                "asset_id": source_path.stem,
                "source_file": source_path.name,
                "buildable": buildable,
                "reason": reason,
            }
        )

    return pending


def _poll_process() -> None:
    global _ACTIVE_PROCESS
    if _ACTIVE_PROCESS is not None and _ACTIVE_PROCESS.poll() is not None:
        _ACTIVE_PROCESS = None


def ensure_auto_ingest_started(force: bool = False) -> dict[str, Any]:
    global _ACTIVE_PROCESS, _LAST_LAUNCH_MONO

    with _PROCESS_LOCK:
        _poll_process()
        pending_assets = _collect_pending_assets()

        if not SPARK_AUTO_INGEST:
            pass
        elif _ACTIVE_PROCESS is not None:
            pass
        elif not pending_assets:
            pass
        else:
            now = time.monotonic()
            if force or (now - _LAST_LAUNCH_MONO) >= _MIN_RELAUNCH_INTERVAL_SEC:
                command = [
                    sys.executable,
                    str(BASE_DIR / "tools" / "build_spark_assets.py"),
                    "sync",
                    "--variant",
                    SPARK_AUTO_VARIANT,
                    "--spark-root",
                    str(SPARK_ROOT),
                ]
                creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
                _ACTIVE_PROCESS = subprocess.Popen(
                    command,
                    cwd=str(BASE_DIR),
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    creationflags=creationflags,
                )
                _LAST_LAUNCH_MONO = now

    return get_auto_ingest_status()


def get_auto_ingest_status() -> dict[str, Any]:
    with _PROCESS_LOCK:
        _poll_process()
        pending_assets = _collect_pending_assets()
        status_data = _read_json(SPARK_STATUS_FILE) or {}

        running = _ACTIVE_PROCESS is not None
        summary = status_data.get("summary")
        if not isinstance(summary, dict):
            summary = {}

        assets = status_data.get("assets")
        if not isinstance(assets, dict):
            assets = {}

        active_asset = ""
        if running:
            for asset_id, payload in assets.items():
                if isinstance(payload, dict) and payload.get("state") == "building":
                    active_asset = str(asset_id)
                    break

    return {
        "enabled": SPARK_AUTO_INGEST,
        "running": running,
        "variant": SPARK_AUTO_VARIANT,
        "spark_root": str(SPARK_ROOT),
        "spark_root_exists": SPARK_ROOT.exists(),
        "status_file": str(SPARK_STATUS_FILE),
        "pending_assets": pending_assets,
        "pending_count": len(pending_assets),
        "active_asset": active_asset,
        "summary": summary,
        "last_status": status_data,
    }
