from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    query: str = Field(..., min_length=1)


class McpRenderRequest(BaseModel):
    cif_path: str = Field(..., min_length=1)


class ThreeDGSRenderRequest(BaseModel):
    filename: str = Field(..., min_length=1)
    quality: str = "auto"


class MetricRequest(BaseModel):
    payload: dict[str, Any] = Field(default_factory=dict)
