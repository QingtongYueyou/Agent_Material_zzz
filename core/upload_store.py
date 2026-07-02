from __future__ import annotations

import base64
import hashlib
import json
import re
import secrets
import shutil
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from config.settings import (
    FILE_INTROSPECTION_CACHE_DIR,
    MCP_ALLOWED_UPLOAD_EXTENSIONS,
    MCP_MAX_UPLOAD_MB,
    MCP_UPLOAD_DIR,
)


class UploadStoreError(RuntimeError):
    pass


class UploadValidationError(UploadStoreError, ValueError):
    pass


class UploadNotFoundError(UploadStoreError, FileNotFoundError):
    pass


FILE_ID_RE = re.compile(r"^file_\d{8}_[a-f0-9]{16}$")
METADATA_FILENAME = "metadata.json"
STORED_FILENAME = "original"
INTROSPECTION_CACHE_FILENAME_TEMPLATE = "introspection.v{version}.json"


def _upload_root() -> Path:
    root = Path(MCP_UPLOAD_DIR).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _validate_file_id(file_id: str) -> str:
    if not isinstance(file_id, str) or not FILE_ID_RE.fullmatch(file_id):
        raise UploadValidationError(f"Invalid file_id: {file_id!r}")
    return file_id


def _new_file_id() -> str:
    return f"file_{datetime.utcnow().strftime('%Y%m%d')}_{secrets.token_hex(8)}"


def _safe_original_filename(filename: str) -> str:
    if not isinstance(filename, str) or not filename.strip():
        raise UploadValidationError("filename is required.")

    normalized = filename.strip()
    if "/" in normalized or "\\" in normalized:
        raise UploadValidationError("filename must not contain path separators.")

    name = Path(normalized).name
    if name in {"", ".", ".."}:
        raise UploadValidationError("filename is invalid.")
    return name


def _allowed_extensions() -> set[str]:
    return {str(extension).lower() for extension in MCP_ALLOWED_UPLOAD_EXTENSIONS}


def _validate_extension(filename: str) -> str:
    extension = Path(filename).suffix.lower()
    if not extension:
        raise UploadValidationError("filename must include an extension.")
    if extension not in _allowed_extensions():
        raise UploadValidationError(f"File extension {extension!r} is not allowed.")
    return extension


def _validate_size(size_bytes: int) -> None:
    max_bytes = int(MCP_MAX_UPLOAD_MB) * 1024 * 1024
    if size_bytes > max_bytes:
        raise UploadValidationError(
            f"File is too large: {size_bytes} bytes exceeds {max_bytes} bytes."
        )


def _metadata_path(file_id: str) -> Path:
    file_id = _validate_file_id(file_id)
    path = (_upload_root() / file_id / METADATA_FILENAME).resolve()
    if not _is_relative_to(path, _upload_root()):
        raise UploadValidationError("Resolved metadata path escaped upload directory.")
    return path


def _write_metadata(metadata: dict[str, Any]) -> None:
    metadata_path = _metadata_path(metadata["file_id"])
    metadata_path.parent.mkdir(parents=True, exist_ok=True)
    metadata_path.write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def _build_metadata(
    *,
    file_id: str,
    original_filename: str,
    stored_filename: str,
    extension: str,
    mime_type: str | None,
    size_bytes: int,
    sha256: str,
    source: str,
) -> dict[str, Any]:
    return {
        "file_id": file_id,
        "source": source,
        "original_filename": original_filename,
        "filename": original_filename,
        "stored_filename": stored_filename,
        "extension": extension,
        "mime_type": mime_type,
        "size_bytes": size_bytes,
        "sha256": sha256,
        "created_at": time.time(),
    }


def save_upload_file(
    filename: str,
    content: bytes,
    mime_type: str | None = None,
    source: str = "user_upload",
) -> dict[str, Any]:
    if not isinstance(content, (bytes, bytearray)):
        raise UploadValidationError("content must be bytes.")

    original_filename = _safe_original_filename(filename)
    extension = _validate_extension(original_filename)
    payload = bytes(content)
    _validate_size(len(payload))

    file_id = _new_file_id()
    stored_filename = f"{STORED_FILENAME}{extension}"
    directory = (_upload_root() / file_id).resolve()
    if not _is_relative_to(directory, _upload_root()):
        raise UploadValidationError("Resolved file path escaped upload directory.")

    directory.mkdir(parents=True, exist_ok=False)
    stored_path = (directory / stored_filename).resolve()
    if not _is_relative_to(stored_path, _upload_root()):
        raise UploadValidationError("Resolved file path escaped upload directory.")

    stored_path.write_bytes(payload)
    metadata = _build_metadata(
        file_id=file_id,
        original_filename=original_filename,
        stored_filename=stored_filename,
        extension=extension,
        mime_type=mime_type,
        size_bytes=len(payload),
        sha256=hashlib.sha256(payload).hexdigest(),
        source=source,
    )
    _write_metadata(metadata)
    return metadata


def register_existing_file(
    path: str | Path,
    original_filename: str | None = None,
    source: str = "system_generated",
) -> dict[str, Any]:
    source_path = Path(path).expanduser().resolve()
    if not source_path.exists() or not source_path.is_file():
        raise UploadNotFoundError(f"File does not exist: {source_path}")

    filename = _safe_original_filename(original_filename or source_path.name)
    extension = _validate_extension(filename)
    size_bytes = source_path.stat().st_size
    _validate_size(size_bytes)

    file_id = _new_file_id()
    stored_filename = f"{STORED_FILENAME}{extension}"
    directory = (_upload_root() / file_id).resolve()
    if not _is_relative_to(directory, _upload_root()):
        raise UploadValidationError("Resolved file path escaped upload directory.")

    directory.mkdir(parents=True, exist_ok=False)
    stored_path = (directory / stored_filename).resolve()
    if not _is_relative_to(stored_path, _upload_root()):
        raise UploadValidationError("Resolved file path escaped upload directory.")

    shutil.copyfile(source_path, stored_path)
    payload = stored_path.read_bytes()
    metadata = _build_metadata(
        file_id=file_id,
        original_filename=filename,
        stored_filename=stored_filename,
        extension=extension,
        mime_type=None,
        size_bytes=len(payload),
        sha256=hashlib.sha256(payload).hexdigest(),
        source=source,
    )
    _write_metadata(metadata)
    return metadata


def get_file_metadata(file_id: str) -> dict[str, Any]:
    metadata_path = _metadata_path(file_id)
    if not metadata_path.exists() or not metadata_path.is_file():
        raise UploadNotFoundError(f"File metadata not found for {file_id!r}.")

    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise UploadValidationError(f"Metadata is invalid for {file_id!r}.") from exc

    if not isinstance(metadata, dict):
        raise UploadValidationError(f"Metadata is invalid for {file_id!r}.")
    if metadata.get("file_id") != file_id:
        raise UploadValidationError(f"Metadata file_id mismatch for {file_id!r}.")
    return metadata


def resolve_file_path(file_id: str) -> Path:
    metadata = get_file_metadata(file_id)
    stored_filename = metadata.get("stored_filename")
    if not isinstance(stored_filename, str) or not stored_filename:
        raise UploadValidationError(f"stored_filename is missing for {file_id!r}.")
    if "/" in stored_filename or "\\" in stored_filename:
        raise UploadValidationError(f"stored_filename is invalid for {file_id!r}.")

    root = _upload_root()
    path = (root / file_id / stored_filename).resolve()
    if not _is_relative_to(path, root):
        raise UploadValidationError("Resolved file path escaped upload directory.")
    if not path.exists() or not path.is_file():
        raise UploadNotFoundError(f"Stored file not found for {file_id!r}.")
    return path


def read_file_base64(file_id: str) -> tuple[dict[str, Any], str]:
    metadata = get_file_metadata(file_id)
    path = resolve_file_path(file_id)
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return metadata, encoded


def get_introspection_cache_path(file_id: str, *, parser_version: str = "1") -> Path | None:
    """Return the per-file introspection cache path if it exists; else None.

    The caller (core.file_introspection) is responsible for writing this path;
    this helper exists so the cache-file naming convention lives in one place.
    """
    file_id = _validate_file_id(file_id)
    filename = INTROSPECTION_CACHE_FILENAME_TEMPLATE.format(version=parser_version)
    path = (_upload_root() / file_id / filename).resolve()
    if not _is_relative_to(path, _upload_root()):
        return None
    if not path.exists() or not path.is_file():
        return None
    return path


def resolve_introspection_cache_path(file_id: str, *, parser_version: str = "1") -> Path | None:
    """Return the per-file introspection cache path (creating it is the caller's job).

    Used by core.file_introspection to compute the write target. Returns None
    if the resolved path would escape the upload root.
    """
    try:
        file_id = _validate_file_id(file_id)
    except UploadValidationError:
        return None
    filename = INTROSPECTION_CACHE_FILENAME_TEMPLATE.format(version=parser_version)
    path = (_upload_root() / file_id / filename).resolve()
    if not _is_relative_to(path, _upload_root()):
        return None
    return path


def resolve_global_introspection_cache_path(sha256: str) -> Path | None:
    """Return the sha256-keyed global cache path inside FILE_INTROSPECTION_CACHE_DIR.

    Returns None when the supplied sha256 is malformed or the resolved path would
    escape the cache root. The sha256 must be a 64-character lowercase hex string.
    """
    if not isinstance(sha256, str) or not sha256:
        return None
    candidate = sha256.strip().lower()
    if not re.fullmatch(r"[0-9a-f]{64}", candidate):
        return None
    root = Path(FILE_INTROSPECTION_CACHE_DIR).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    filename = f"{candidate}.v1.json"
    path = (root / filename).resolve()
    if not _is_relative_to(path, root):
        return None
    return path


def get_global_introspection_cache_path(sha256: str) -> Path | None:
    """Return the global cache path if it exists; else None. See resolve_global_introspection_cache_path."""
    path = resolve_global_introspection_cache_path(sha256)
    if path is None:
        return None
    if not path.exists() or not path.is_file():
        return None
    return path
