from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=10000)
    file_ids: list[str] = Field(default_factory=list, max_length=10)


class UploadedFileResponse(BaseModel):
    file_id: str
    filename: str
    extension: str
    mime_type: str | None = None
    size_bytes: int
    sha256: str
    created_at: float
    source: str = "user_upload"


class McpRenderRequest(BaseModel):
    cif_path: str = Field(..., min_length=1)


class ThreeDGSRenderRequest(BaseModel):
    filename: str = Field(..., min_length=1)
    quality: str = "auto"
    render_profile: str = "performance"


class VisualizationRenderRequest(BaseModel):
    intent: str = Field(..., min_length=1)
    input_type: Literal["file", "asset"] | None = None
    file_id: str | None = None
    filename: str | None = None
    quality: Literal["auto", "preview", "balanced", "full", "source"] = "auto"
    render_profile: Literal["performance", "quality"] = "performance"


class MetricRequest(BaseModel):
    payload: dict[str, Any] = Field(default_factory=dict)
