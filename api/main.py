from __future__ import annotations

import json
from importlib import import_module
from collections.abc import Generator
from pathlib import Path
from typing import Any
from urllib.parse import quote

from fastapi import FastAPI, HTTPException, Query, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from api.files import router as files_router
from api.schemas import (
    ChatRequest,
    McpRenderRequest,
    MetricRequest,
    ThreeDGSRenderRequest,
    VisualizationRenderRequest,
)
from api.serialization import serialize_workflow_event
from config.settings import (
    BASE_DIR,
    CIF_DIR,
    CORS_ALLOWED_ORIGINS,
    MCP_ENABLED,
    MCP_REFRESH_SKEW_SEC,
    MCP_TOOL_GATEWAY_ENABLED,
    STATIC_DIR,
    THREEDGS_MCP_ENABLED,
    THREEDGS_MCP_SERVER_URL,
    THREEDGS_RENDER_TTL_SEC,
)
from core.mcp_client import MCPClientError, process_file
from core.mcp_router import ROUTE_TABLE
from core.perf_metrics import append_interaction_metric, append_render_metric
from core.spark_asset_ingest import ensure_auto_ingest_started, get_auto_ingest_status
from core.splat_assets import resolve_splat_asset
from core.tools import execute_openai_tool
from core.workflow import WorkflowOrchestrator


_3dgs_mcp_client = import_module("core.3dgs_mcp_client")
ThreeDGSMCPClientError = _3dgs_mcp_client.ThreeDGSMCPClientError
create_3dgs_render = _3dgs_mcp_client.create_render

app = FastAPI(
    title="Agent Material Backend",
    version="0.2.0",
    description="Backend API for the separated materials analysis frontend.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ALLOWED_ORIGINS,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
app.include_router(files_router)

_SERVED_ASSET_SUFFIXES = {".ksplat", ".ply", ".rad", ".radc", ".splat", ".spz"}
_ASSET_ROOTS = (STATIC_DIR.resolve(),)


@app.on_event("startup")
def startup() -> None:
    ensure_auto_ingest_started()


@app.exception_handler(Exception)
def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "detail": "Internal application service error.",
            "error_type": exc.__class__.__name__,
            "path": str(request.url.path),
        },
    )


@app.get("/health")
def health() -> dict[str, Any]:
    return {
        "ok": True,
        "service": "agent-material-backend",
        "mode": "frontend-backend",
        "asset_pipeline": get_auto_ingest_status(),
        "mcp": {
            "enabled": MCP_ENABLED,
            "refresh_skew_sec": MCP_REFRESH_SKEW_SEC,
        },
        "3dgs_mcp": {
            "enabled": THREEDGS_MCP_ENABLED,
            "server_url": THREEDGS_MCP_SERVER_URL,
            "ttl_sec": THREEDGS_RENDER_TTL_SEC,
        },
    }


def _sse_line(payload: dict[str, Any]) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _chat_event_stream(query: str, file_ids: list[str] | None = None) -> Generator[str, None, None]:
    try:
        orchestrator = WorkflowOrchestrator()
        for event in orchestrator.run_stream(query, file_ids=file_ids):
            yield _sse_line(serialize_workflow_event(event))
    except Exception as exc:
        yield _sse_line(
            {
                "type": "error",
                "detail": str(exc),
                "error_type": exc.__class__.__name__,
            }
        )


@app.post("/api/chat/stream")
def chat_stream(request: ChatRequest) -> StreamingResponse:
    return StreamingResponse(
        _chat_event_stream(request.query, request.file_ids),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/api/chat")
def chat(request: ChatRequest) -> dict[str, Any]:
    events: list[dict[str, Any]] = []
    for raw_line in _chat_event_stream(request.query, request.file_ids):
        payload = raw_line.removeprefix("data: ").strip()
        if payload:
            events.append(json.loads(payload))
    return {"events": events, "final": next((e for e in reversed(events) if e.get("type") == "final"), None)}


def _asset_model_url(url_path: str, file_mtime: int) -> str:
    if url_path.startswith("static/"):
        return f"/{url_path}?v={file_mtime}"
    return f"/api/assets/file/{quote(url_path, safe='/')}?v={file_mtime}"


def _resolve_asset_file(relative_path: str) -> Path:
    candidate = Path(relative_path)
    if candidate.is_absolute():
        raise HTTPException(status_code=400, detail="Asset path must be relative.")

    resolved = (BASE_DIR / candidate).resolve()
    if not any(_is_relative_to(resolved, root) for root in _ASSET_ROOTS):
        raise HTTPException(status_code=400, detail="Asset path must be inside static assets.")

    if resolved.suffix.lower() not in _SERVED_ASSET_SUFFIXES:
        raise HTTPException(status_code=404, detail="Unsupported asset file type.")
    if not resolved.exists() or not resolved.is_file():
        raise HTTPException(status_code=404, detail="Asset file not found.")
    return resolved


@app.get("/api/assets/file/{relative_path:path}")
def asset_file(relative_path: str) -> FileResponse:
    return FileResponse(_resolve_asset_file(relative_path))


@app.get("/api/assets/splat/{filename:path}")
def splat_asset(
    filename: str,
    quality: str = Query(default="auto", pattern="^(auto|preview|balanced|full|source)$"),
) -> dict[str, Any]:
    asset = resolve_splat_asset(filename, quality_preference=quality)
    if asset is None:
        raise HTTPException(status_code=404, detail="No matching splat asset found.")

    model_url = _asset_model_url(str(asset["url_path"]), int(asset["file_mtime"]))
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
        "recommended_quality": asset.get("recommended_quality"),
        "recommended_render_profile": asset.get("recommended_render_profile"),
        "warnings": asset.get("warnings") or [],
    }


@app.get("/api/assets/pipeline")
def asset_pipeline() -> dict[str, Any]:
    return get_auto_ingest_status()


@app.get("/api/cif")
def cif_file(path: str = Query(..., min_length=1)) -> FileResponse:
    resolved = _resolve_cif_path(path)
    return FileResponse(resolved, media_type="chemical/x-cif", filename=resolved.name)


def _resolve_cif_path(raw_path: str) -> Path:
    candidate = Path(raw_path)
    if candidate.suffix.lower() != ".cif":
        raise HTTPException(status_code=400, detail="CIF path must point to a .cif file.")

    if candidate.is_absolute():
        resolved = candidate.resolve()
    else:
        if candidate.name != raw_path:
            raise HTTPException(status_code=400, detail="CIF path must be a filename.")
        resolved = (CIF_DIR / candidate.name).resolve()

    try:
        resolved.relative_to(CIF_DIR.resolve())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="CIF path must be inside cif_files.") from exc

    if not resolved.exists() or not resolved.is_file():
        raise HTTPException(status_code=404, detail="CIF file not found.")
    return resolved


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


@app.post("/api/mcp/render")
def mcp_render(request: McpRenderRequest) -> dict[str, Any]:
    if not MCP_ENABLED:
        raise HTTPException(status_code=503, detail="MCP visualization is disabled.")

    path = _resolve_cif_path(request.cif_path)
    try:
        return process_file(path)
    except MCPClientError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.post("/api/3dgs/render")
def three_dgs_render(request: ThreeDGSRenderRequest) -> dict[str, Any]:
    if not THREEDGS_MCP_ENABLED:
        raise HTTPException(status_code=503, detail="3DGS MCP rendering is disabled.")

    try:
        return create_3dgs_render(
            request.filename,
            quality=request.quality,
            render_profile=request.render_profile,
        )
    except ThreeDGSMCPClientError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.get("/api/visualizations/capabilities")
def visualization_capabilities() -> dict[str, Any]:
    capabilities = [
        {
            "intent": "3dgs",
            "title": "3D Gaussian Splatting",
            "provider": "local-3dgs-mcp",
            "tool": "3dgs.create_render",
            "input_type": "asset",
            "extensions": [".ksplat", ".ply", ".rad", ".splat", ".spz"],
            "enabled": THREEDGS_MCP_ENABLED,
        }
    ]
    capabilities.extend(
        {
            "intent": intent,
            "title": str(route["title"]),
            "provider": str(route["server_name"]),
            "tool": str(route["file_tool"]),
            "input_type": "file",
            "extensions": sorted(str(extension) for extension in route["extensions"]),
            "enabled": MCP_TOOL_GATEWAY_ENABLED,
        }
        for intent, route in ROUTE_TABLE.items()
    )
    return {"capabilities": capabilities}


@app.post("/api/visualizations/render")
def render_visualization(request: VisualizationRenderRequest) -> dict[str, Any]:
    intent = request.intent.strip().lower()
    if intent == "3dgs":
        if request.input_type not in {None, "asset"}:
            raise HTTPException(status_code=400, detail="3dgs visualization requires input_type='asset'.")
        filename = (request.filename or "").strip()
        if not filename:
            raise HTTPException(status_code=400, detail="filename is required for 3dgs visualization.")
        if not THREEDGS_MCP_ENABLED:
            raise HTTPException(status_code=503, detail="3DGS MCP rendering is disabled.")
        try:
            result = create_3dgs_render(
                filename,
                quality=request.quality,
                render_profile=request.render_profile,
            )
        except ThreeDGSMCPClientError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        return {
            **result,
            "ok": True,
            "intent": "3dgs",
            "provider": "local-3dgs-mcp",
            "tool": "3dgs.create_render",
            "display": "iframe",
        }

    route = ROUTE_TABLE.get(intent)
    if route is None:
        allowed = ", ".join(["3dgs", *ROUTE_TABLE.keys()])
        raise HTTPException(status_code=400, detail=f"Unsupported visualization intent. Allowed intents: {allowed}.")
    if request.input_type not in {None, "file"}:
        raise HTTPException(status_code=400, detail="External MCP visualization requires input_type='file'.")
    file_id = (request.file_id or "").strip()
    if not file_id:
        raise HTTPException(status_code=400, detail="file_id is required for external MCP visualization.")
    if not MCP_TOOL_GATEWAY_ENABLED:
        raise HTTPException(status_code=503, detail="MCP tool gateway is disabled.")

    result = execute_openai_tool(
        "render_with_mcp",
        {"intent": intent, "input_type": "file", "file_id": file_id},
    )
    if not isinstance(result, dict) or result.get("error"):
        detail = result.get("error") if isinstance(result, dict) else "Invalid MCP render result."
        raise HTTPException(status_code=502, detail=str(detail))
    return {
        **result,
        "ok": True,
        "provider": str(route["server_name"]),
        "tool": str(route["file_tool"]),
    }


@app.post("/api/metrics/render")
def render_metrics(request: MetricRequest) -> dict[str, bool]:
    append_render_metric(request.payload)
    return {"ok": True}


@app.post("/api/metrics/interaction")
def interaction_metrics(request: MetricRequest) -> dict[str, bool]:
    append_interaction_metric(request.payload)
    return {"ok": True}
