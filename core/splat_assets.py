from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from config.settings import BASE_DIR, SPLAT_DERIVED_DIR, SPLAT_DIR, SPLAT_SOURCE_DIR
from core.ply_utils import get_ply_bounds, get_ply_vertex_count


def _candidate_asset_keys(filename: str) -> list[str]:
    stem = Path(filename).stem
    parts = stem.split("_", 1)
    material_name = parts[0]
    formula_name = parts[1] if len(parts) > 1 else ""

    keys = [stem, material_name]
    if formula_name:
        keys.append(formula_name)
    keys.append("object")

    deduped: list[str] = []
    for key in keys:
        if key and key not in deduped:
            deduped.append(key)
    return deduped


def _safe_relative_to_base(path: Path) -> str | None:
    try:
        return path.resolve().relative_to(BASE_DIR.resolve()).as_posix()
    except ValueError:
        return None


def _manifest_candidates(asset_id: str) -> list[Path]:
    return [
        SPLAT_DERIVED_DIR / asset_id / f"{asset_id}.manifest.json",
        SPLAT_DIR / f"{asset_id}.manifest.json",
    ]


def _direct_asset_roots() -> list[Path]:
    roots = [SPLAT_SOURCE_DIR, SPLAT_DERIVED_DIR, SPLAT_DIR]
    deduped: list[Path] = []
    for root in roots:
        if root not in deduped:
            deduped.append(root)
    return deduped


def _resolve_asset_path(raw_path: str, manifest_path: Path | None = None) -> Path | None:
    candidate = Path(raw_path)
    search_roots = []

    if candidate.is_absolute():
        search_roots.append(candidate)
    else:
        if manifest_path is not None:
            search_roots.append((manifest_path.parent / candidate).resolve())
        search_roots.append((SPLAT_SOURCE_DIR / candidate).resolve())
        search_roots.append((SPLAT_DERIVED_DIR / candidate).resolve())
        search_roots.append((SPLAT_DIR / candidate).resolve())
        search_roots.append((BASE_DIR / candidate).resolve())

    for path in search_roots:
        if path.exists() and _safe_relative_to_base(path) is not None:
            return path
    return None


def _read_manifest(path: Path) -> dict[str, Any] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None

    return data if isinstance(data, dict) else None


def _build_asset_record(
    path: Path,
    *,
    asset_id: str,
    variant_name: str,
    source_kind: str,
    manifest_name: str | None,
    selection_note: str,
    enable_lod: bool | None = None,
    enable_paged: bool | None = None,
) -> dict[str, Any] | None:
    url_path = _safe_relative_to_base(path)
    if url_path is None:
        return None

    model_format = path.suffix.lstrip(".").lower()
    vertex_count = get_ply_vertex_count(path)
    file_size_bytes = path.stat().st_size
    is_large_model = (
        file_size_bytes >= 100 * 1024 * 1024
        or (vertex_count is not None and vertex_count >= 1_000_000)
    )

    if enable_lod is None:
        enable_lod = is_large_model and model_format != "rad"
    if enable_paged is None:
        enable_paged = model_format == "rad"

    if model_format == "rad":
        lod_mode_label = "RAD paged LoD" if enable_paged else "RAD prebuilt LoD"
    elif enable_lod:
        lod_mode_label = "dynamic LoD"
    else:
        lod_mode_label = "full detail"

    return {
        "asset_id": asset_id,
        "variant_name": variant_name,
        "source_kind": source_kind,
        "manifest_name": manifest_name or "",
        "selection_note": selection_note,
        "path": path,
        "url_path": url_path,
        "model_name": path.name,
        "model_format": model_format,
        "vertex_count": vertex_count,
        "vertex_count_label": "unknown" if vertex_count is None else str(vertex_count),
        "file_size_bytes": file_size_bytes,
        "file_mtime": int(path.stat().st_mtime),
        "is_large_model": is_large_model,
        "enable_lod": enable_lod,
        "enable_paged": enable_paged,
        "lod_mode_label": lod_mode_label,
    }


def _select_manifest_asset(manifest_path: Path, quality_preference: str) -> dict[str, Any] | None:
    manifest = _read_manifest(manifest_path)
    if not manifest:
        return None

    asset_id = str(manifest.get("asset_id") or manifest_path.name.replace(".manifest.json", ""))
    raw_variants = manifest.get("variants")
    variants = raw_variants if isinstance(raw_variants, dict) else {}

    requested_quality = quality_preference if quality_preference != "auto" else ""
    selection_order: list[str] = []

    if requested_quality:
        selection_order.append(requested_quality)

    default_variant = str(manifest.get("default_variant") or "").strip()
    for name in [default_variant, "balanced", "preview", "full", "source"]:
        if name and name not in selection_order:
            selection_order.append(name)

    for name in variants:
        if isinstance(name, str) and name not in selection_order:
            selection_order.append(name)

    for variant_name in selection_order:
        payload = variants.get(variant_name)
        if not isinstance(payload, dict):
            continue

        raw_path = payload.get("path") or payload.get("file") or payload.get("relative_path")
        if not isinstance(raw_path, str) or not raw_path.strip():
            continue

        resolved_path = _resolve_asset_path(raw_path, manifest_path)
        if resolved_path is None:
            continue

        selection_note = f"Manifest '{manifest_path.name}' -> variant '{variant_name}'"
        if requested_quality and variant_name != requested_quality:
            selection_note = (
                f"Requested quality '{requested_quality}' unavailable; using '{variant_name}'"
            )

        asset_record = _build_asset_record(
            resolved_path,
            asset_id=asset_id,
            variant_name=variant_name,
            source_kind="manifest",
            manifest_name=manifest_path.name,
            selection_note=selection_note,
            enable_lod=bool(payload.get("lod")) if "lod" in payload else None,
            enable_paged=bool(payload.get("paged")) if "paged" in payload else None,
        )
        if asset_record is None:
            continue

        raw_source_path = payload.get("source_path")
        if not isinstance(raw_source_path, str) or not raw_source_path.strip():
            source_payload = variants.get("source")
            if isinstance(source_payload, dict):
                source_candidate = source_payload.get("path") or source_payload.get("file")
                raw_source_path = source_candidate if isinstance(source_candidate, str) else ""

        if raw_source_path:
            source_path = _resolve_asset_path(raw_source_path, manifest_path)
            if source_path is not None:
                asset_record["view_bounds"] = get_ply_bounds(source_path)

        return asset_record

    return None


def _resolve_direct_asset(filename: str) -> dict[str, Any] | None:
    suffixes = [".rad", ".ply", ".spz", ".splat", ".ksplat"]

    for key in _candidate_asset_keys(filename):
        exact_candidates: list[Path] = []
        for root in _direct_asset_roots():
            exact_candidates.append(root / f"{key}-lod.rad")
            exact_candidates.extend(root / f"{key}{suffix}" for suffix in suffixes)

        for candidate in exact_candidates:
            if candidate.exists():
                return _build_asset_record(
                    candidate,
                    asset_id=Path(filename).stem,
                    variant_name="direct",
                    source_kind="direct",
                    manifest_name=None,
                    selection_note=f"No manifest found; using direct asset '{candidate.name}'",
                )

        for root in _direct_asset_roots():
            for pattern in (f"*{key}*-lod.rad", f"*{key}*.rad", f"*{key}*.ply"):
                matches = sorted(root.rglob(pattern))
                if matches:
                    return _build_asset_record(
                        matches[0],
                        asset_id=Path(filename).stem,
                        variant_name="direct",
                        source_kind="direct",
                        manifest_name=None,
                        selection_note=f"No manifest found; using glob match '{matches[0].name}'",
                    )

    return None


def resolve_splat_asset(filename: str, quality_preference: str = "auto") -> dict[str, Any] | None:
    for key in _candidate_asset_keys(filename):
        for manifest_path in _manifest_candidates(key):
            if not manifest_path.exists():
                continue

            asset_record = _select_manifest_asset(manifest_path, quality_preference)
            if asset_record is not None:
                return asset_record

    return _resolve_direct_asset(filename)
