from __future__ import annotations

from importlib import import_module
from typing import Any

from fastapi import APIRouter, File, HTTPException, UploadFile, status

from api.schemas import UploadedFileResponse


router = APIRouter()


def _get_upload_store() -> Any:
    try:
        return import_module("core.upload_store")
    except ImportError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Upload store is unavailable.",
        ) from exc


def _normalize_upload_metadata(metadata: dict[str, Any]) -> UploadedFileResponse:
    filename = metadata.get("filename") or metadata.get("original_filename") or metadata.get("stored_filename")
    return UploadedFileResponse(
        file_id=str(metadata.get("file_id") or ""),
        filename=str(filename or ""),
        extension=str(metadata.get("extension") or ""),
        mime_type=metadata.get("mime_type"),
        size_bytes=int(metadata.get("size_bytes") or 0),
        sha256=str(metadata.get("sha256") or ""),
        created_at=float(metadata.get("created_at") or 0),
        source=str(metadata.get("source") or "user_upload"),
    )


@router.post("/api/files/upload", response_model=UploadedFileResponse)
async def upload_file(file: UploadFile = File(...)) -> UploadedFileResponse:
    content = await file.read()
    upload_store = _get_upload_store()
    try:
        metadata = upload_store.save_upload_file(
            file.filename or "upload",
            content,
            mime_type=file.content_type,
            source="user_upload",
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    if not isinstance(metadata, dict):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Upload store returned invalid metadata.",
        )
    return _normalize_upload_metadata(metadata)
