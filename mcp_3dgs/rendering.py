from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from threading import Lock
from typing import Any
from urllib.parse import quote

from config.settings import (
    SPLAT_DIR,
    THREEDGS_PUBLIC_BASE_URL,
    THREEDGS_RENDER_TTL_SEC,
    THREEDGS_SESSION_FILE,
)
from core.splat_assets import resolve_splat_asset


ALLOWED_ASSET_SUFFIXES = {".ksplat", ".ply", ".rad", ".radc", ".splat", ".spz"}
DEFAULT_QUALITY = "auto"


@dataclass(frozen=True)
class RenderSession:
    session_id: str
    filename: str
    quality: str
    created_at: float
    expires_at: float
    ttl_sec: int
    asset: dict[str, Any]
    render_url: str


class AssetPathError(ValueError):
    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


class RenderCreateError(ValueError):
    pass


class SessionNotFoundError(LookupError):
    pass


class SessionExpiredError(LookupError):
    pass


sessions: dict[str, RenderSession] = {}
_SESSION_LOCK = Lock()


def _now() -> float:
    return time.time()


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _public_base_url() -> str:
    return THREEDGS_PUBLIC_BASE_URL.rstrip("/")


def _session_to_dict(session: RenderSession) -> dict[str, Any]:
    return {
        "session_id": session.session_id,
        "filename": session.filename,
        "quality": session.quality,
        "created_at": session.created_at,
        "expires_at": session.expires_at,
        "ttl_sec": session.ttl_sec,
        "asset": session.asset,
        "render_url": session.render_url,
    }


def _session_from_dict(payload: dict[str, Any]) -> RenderSession | None:
    try:
        asset = payload["asset"]
        if not isinstance(asset, dict):
            return None
        return RenderSession(
            session_id=str(payload["session_id"]),
            filename=str(payload["filename"]),
            quality=str(payload["quality"]),
            created_at=float(payload["created_at"]),
            expires_at=float(payload["expires_at"]),
            ttl_sec=int(payload["ttl_sec"]),
            asset=asset,
            render_url=str(payload["render_url"]),
        )
    except (KeyError, TypeError, ValueError):
        return None


def load_sessions() -> None:
    with _SESSION_LOCK:
        try:
            raw = json.loads(THREEDGS_SESSION_FILE.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            raw = {}

        loaded: dict[str, RenderSession] = {}
        items = raw.get("sessions") if isinstance(raw, dict) else []
        if isinstance(items, list):
            for item in items:
                if not isinstance(item, dict):
                    continue
                session = _session_from_dict(item)
                if session is not None:
                    loaded[session.session_id] = session
        sessions.clear()
        sessions.update(loaded)


def save_sessions() -> None:
    with _SESSION_LOCK:
        THREEDGS_SESSION_FILE.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema_version": 1,
            "sessions": [_session_to_dict(session) for session in sessions.values()],
        }
        temp_path = THREEDGS_SESSION_FILE.with_suffix(".tmp")
        temp_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        temp_path.replace(THREEDGS_SESSION_FILE)


def validate_lookup_filename(filename: str) -> str:
    value = filename.strip()
    if not value:
        raise RenderCreateError("filename is required.")

    candidate = Path(value)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise RenderCreateError("filename must be a relative asset lookup name.")

    return value


def resolve_asset_relative_path(relative_path: str) -> Path:
    candidate = Path(relative_path)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise AssetPathError("Asset path must be relative.", status_code=400)

    resolved = (SPLAT_DIR / candidate).resolve()
    splat_root = SPLAT_DIR.resolve()
    if not _is_relative_to(resolved, splat_root):
        raise AssetPathError("Asset path must stay inside static/splat_files.", status_code=400)

    if resolved.suffix.lower() not in ALLOWED_ASSET_SUFFIXES:
        raise AssetPathError("Unsupported asset file type.", status_code=404)
    if not resolved.exists() or not resolved.is_file():
        raise AssetPathError("Asset file not found.", status_code=404)
    return resolved


def resolved_asset_path(asset: dict[str, Any]) -> Path:
    raw_path = asset.get("path")
    if not isinstance(raw_path, Path):
        raw_path = Path(str(raw_path or ""))

    resolved = raw_path.resolve()
    splat_root = SPLAT_DIR.resolve()
    if not _is_relative_to(resolved, splat_root):
        raise RenderCreateError("Resolved asset is outside static/splat_files.")
    if resolved.suffix.lower() not in ALLOWED_ASSET_SUFFIXES:
        raise RenderCreateError("Resolved asset type is not supported.")
    if not resolved.exists() or not resolved.is_file():
        raise RenderCreateError("Resolved asset file does not exist.")
    return resolved


def asset_response(asset: dict[str, Any]) -> dict[str, Any]:
    path = resolved_asset_path(asset)
    relative_path = path.relative_to(SPLAT_DIR.resolve()).as_posix()
    model_url = f"{_public_base_url()}/assets/{quote(relative_path, safe='/')}?v={int(path.stat().st_mtime)}"

    return {
        "asset_id": asset["asset_id"],
        "variant_name": asset["variant_name"],
        "source_kind": asset["source_kind"],
        "manifest_name": asset["manifest_name"],
        "selection_note": asset["selection_note"],
        "model_url": model_url,
        "model_name": asset["model_name"],
        "model_format": asset["model_format"],
        "vertex_count": asset["vertex_count"],
        "vertex_count_label": asset["vertex_count_label"],
        "file_size_bytes": asset["file_size_bytes"],
        "file_mtime": asset["file_mtime"],
        "is_large_model": asset["is_large_model"],
        "enable_lod": asset["enable_lod"],
        "enable_paged": asset["enable_paged"],
        "lod_mode_label": asset["lod_mode_label"],
        "view_bounds": asset.get("view_bounds"),
    }


def session_response(session: RenderSession) -> dict[str, Any]:
    return {
        "ok": True,
        "source": "3dgs:mcp",
        "session_id": session.session_id,
        "render_url": session.render_url,
        "created_at": session.created_at,
        "expires_at": session.expires_at,
        "ttl_sec": session.ttl_sec,
        "asset": session.asset,
    }


def prune_expired_sessions() -> None:
    load_sessions()
    current = _now()
    expired = [session_id for session_id, session in sessions.items() if session.expires_at <= current]
    for session_id in expired:
        sessions.pop(session_id, None)
    if expired:
        save_sessions()


def create_render(filename: str, quality: str = DEFAULT_QUALITY, ttl_sec: int | None = None) -> dict[str, Any]:
    load_sessions()
    lookup_name = validate_lookup_filename(filename)
    quality_name = (quality or DEFAULT_QUALITY).strip() or DEFAULT_QUALITY
    ttl = THREEDGS_RENDER_TTL_SEC if ttl_sec is None else int(ttl_sec)
    if ttl <= 0:
        raise RenderCreateError("ttl_sec must be a positive integer.")

    asset = resolve_splat_asset(lookup_name, quality_preference=quality_name)
    if asset is None:
        raise RenderCreateError("No matching 3DGS splat asset found.")

    session_id = uuid.uuid4().hex
    created_at = _now()
    render_url = f"{_public_base_url()}/viewer/sessions/{session_id}"
    session = RenderSession(
        session_id=session_id,
        filename=lookup_name,
        quality=quality_name,
        created_at=created_at,
        expires_at=created_at + ttl,
        ttl_sec=ttl,
        asset=asset_response(asset),
        render_url=render_url,
    )
    prune_expired_sessions()
    sessions[session_id] = session
    save_sessions()
    return session_response(session)


def get_session_config(session_id: str) -> dict[str, Any]:
    load_sessions()
    session = sessions.get(session_id)
    if session is None:
        raise SessionNotFoundError("Viewer session not found.")
    if session.expires_at <= _now():
        sessions.pop(session_id, None)
        save_sessions()
        raise SessionExpiredError("Viewer session has expired.")
    return session_response(session)
