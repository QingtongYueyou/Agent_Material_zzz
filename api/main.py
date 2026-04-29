from __future__ import annotations

from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from config.settings import PLAN_API_TOKEN
from core.planner import create_tool_plan
from core.planner_schema import DEFAULT_AVAILABLE_TOOLS


app = FastAPI(
    title="Agent Material Planner API",
    version="0.1.0",
    description="Convert natural-language materials requests into server-A executable JSON tool calls.",
)


@app.exception_handler(Exception)
def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "detail": "Internal planner service error.",
            "error_type": exc.__class__.__name__,
            "path": str(request.url.path),
        },
    )


class PlanRequest(BaseModel):
    query: str = Field(..., min_length=1, description="User natural-language instruction.")
    session_id: str | None = Field(default=None, description="Optional server-A session id.")
    context: dict[str, Any] = Field(
        default_factory=dict,
        description="Optional server-A context, including available_tools.",
    )


def _check_auth(authorization: str | None = Header(default=None)) -> None:
    if not PLAN_API_TOKEN:
        return

    expected = f"Bearer {PLAN_API_TOKEN}"
    if authorization != expected:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing bearer token.",
            headers={"WWW-Authenticate": "Bearer"},
        )


@app.get("/health")
def health() -> dict[str, Any]:
    return {
        "ok": True,
        "service": "agent-material-planner",
        "available_tools": DEFAULT_AVAILABLE_TOOLS,
        "auth_required": bool(PLAN_API_TOKEN),
    }


@app.post("/api/v1/plan", dependencies=[Depends(_check_auth)])
def plan(request: PlanRequest) -> dict[str, Any]:
    return create_tool_plan(
        request.query,
        session_id=request.session_id,
        context=request.context,
    )
