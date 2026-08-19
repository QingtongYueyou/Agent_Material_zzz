from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import httpx
from fastapi import FastAPI, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles


DEMO_DIR = Path(__file__).resolve().parent
STATIC_DIR = DEMO_DIR / "static"
UPSTREAM_API_BASE = os.getenv("AGENT_MATERIAL_API_BASE_URL", "http://127.0.0.1:8080").rstrip("/")
UPSTREAM_TIMEOUT_SEC = float(os.getenv("AGENT_MATERIAL_API_TIMEOUT_SEC", "120"))

app = FastAPI(
    title="External Materials Console",
    description="Standalone HTTP consumer for the Agent Material visualization API.",
)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


def _upstream_json(method: str, path: str, **kwargs: Any) -> dict[str, Any]:
    url = f"{UPSTREAM_API_BASE}{path}"
    try:
        with httpx.Client(timeout=UPSTREAM_TIMEOUT_SEC) as client:
            response = client.request(method, url, **kwargs)
    except httpx.RequestError as exc:
        raise HTTPException(status_code=502, detail=f"Agent Material API is unreachable: {exc}") from exc

    try:
        payload = response.json()
    except ValueError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Agent Material API returned a non-JSON response (HTTP {response.status_code}).",
        ) from exc

    if response.is_error:
        detail = payload.get("detail") if isinstance(payload, dict) else payload
        raise HTTPException(status_code=response.status_code, detail=str(detail or "Upstream API request failed."))
    if not isinstance(payload, dict):
        raise HTTPException(status_code=502, detail="Agent Material API returned an invalid JSON payload.")
    return payload


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/upstream/health")
def upstream_health() -> dict[str, Any]:
    return {
        "ok": True,
        "demo_service": "external-materials-console",
        "upstream_base_url": UPSTREAM_API_BASE,
        "upstream": _upstream_json("GET", "/health"),
    }


@app.get("/api/capabilities")
def capabilities() -> dict[str, Any]:
    return _upstream_json("GET", "/api/visualizations/capabilities")


@app.post("/api/files/upload")
async def upload_file(file: UploadFile) -> dict[str, Any]:
    content = await file.read()
    return _upstream_json(
        "POST",
        "/api/files/upload",
        files={
            "file": (
                file.filename or "upload",
                content,
                file.content_type or "application/octet-stream",
            )
        },
    )


@app.post("/api/visualizations/render")
def render_visualization(payload: dict[str, Any]) -> dict[str, Any]:
    return _upstream_json("POST", "/api/visualizations/render", json=payload)


@app.post("/api/chat")
def chat(payload: dict[str, Any]) -> dict[str, Any]:
    return _upstream_json("POST", "/api/chat", json=payload)
