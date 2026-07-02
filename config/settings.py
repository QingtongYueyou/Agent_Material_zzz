from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import urlparse

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parents[1]

load_dotenv(dotenv_path=BASE_DIR / ".env")


def _csv_env(value: str | None) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def _is_production_env(value: str) -> bool:
    return value.strip().lower() in {"prod", "production"}


def _build_cors_allowed_origins(app_env: str, raw_origins: str | None) -> list[str]:
    configured = _csv_env(raw_origins)
    if configured:
        if _is_production_env(app_env):
            allowed = [origin for origin in configured if origin != "*"]
            if not allowed:
                raise RuntimeError("CORS_ALLOWED_ORIGINS must not be '*' in production.")
            return allowed
        return configured

    if _is_production_env(app_env):
        raise RuntimeError("CORS_ALLOWED_ORIGINS must be configured in production.")

    return [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]


def _validate_3dgs_public_base_url(app_env: str, raw_url: str | None) -> str:
    value = (raw_url or "http://127.0.0.1:8090").strip().rstrip("/")
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise RuntimeError("THREEDGS_PUBLIC_BASE_URL must be an absolute http(s) URL.")

    if _is_production_env(app_env) and (parsed.hostname or "").lower() in {
        "127.0.0.1",
        "localhost",
        "0.0.0.0",
    }:
        raise RuntimeError("THREEDGS_PUBLIC_BASE_URL must be browser-accessible in production.")

    return value


CIF_DIR = BASE_DIR / "cif_files"
STATIC_DIR = BASE_DIR / "static"
SPLAT_DIR = STATIC_DIR / "splat_files"
SPLAT_SOURCE_DIR = SPLAT_DIR / "source"
SPLAT_DERIVED_DIR = SPLAT_DIR / "derived"
SPLAT_PIPELINE_DIR = SPLAT_DIR / "_pipeline"
METRICS_DIR = BASE_DIR / "metrics"
METRICS_RAW_DIR = METRICS_DIR / "raw"
RENDER_METRICS_FILE = METRICS_RAW_DIR / "render_metrics.csv"
INTERACTION_METRICS_FILE = METRICS_RAW_DIR / "interaction_metrics.csv"
APP_ENV = (os.getenv("APP_ENV") or os.getenv("ENV") or "development").strip().lower()
CORS_ALLOWED_ORIGINS = _build_cors_allowed_origins(APP_ENV, os.getenv("CORS_ALLOWED_ORIGINS"))
SPARK_STATUS_FILE = SPLAT_PIPELINE_DIR / "spark_asset_pipeline_status.json"
SPARK_AUTO_VARIANT = (os.getenv("SPARK_AUTO_VARIANT", "balanced") or "balanced").strip().lower()
SPARK_AUTO_INGEST = (os.getenv("SPARK_AUTO_INGEST", "true") or "true").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}
MCP_ENABLED = (os.getenv("MCP_ENABLED", "true") or "true").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}
MCP_SERVER_URL = os.getenv("MCP_SERVER_URL", "http://219.232.220.140/view_mcp/mcp")
MCP_API_KEY = os.getenv("MCP_API_KEY", "")
MCP_TIMEOUT_SEC = int(os.getenv("MCP_TIMEOUT_SEC", "60"))
MCP_RENDER_TTL_SEC = int(os.getenv("MCP_RENDER_TTL_SEC", "600"))
MCP_REFRESH_SKEW_SEC = int(os.getenv("MCP_REFRESH_SKEW_SEC", "30"))
MCP_TOOL_GATEWAY_ENABLED = (os.getenv("MCP_TOOL_GATEWAY_ENABLED", "true") or "true").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}
MCP_CONFIG_DIR = Path(os.getenv("MCP_CONFIG_DIR", BASE_DIR / "docs" / "server_json")).expanduser()
MCP_UPLOAD_DIR = Path(os.getenv("MCP_UPLOAD_DIR", STATIC_DIR / "uploads")).expanduser()
MCP_MAX_UPLOAD_MB = int(os.getenv("MCP_MAX_UPLOAD_MB", "100"))
MCP_MAX_FILES_PER_REQUEST = int(os.getenv("MCP_MAX_FILES_PER_REQUEST", "10"))
MCP_ALLOWED_UPLOAD_EXTENSIONS = {
    (extension if extension.startswith(".") else f".{extension}").lower()
    for extension in _csv_env(
        os.getenv(
            "MCP_ALLOWED_UPLOAD_EXTENSIONS",
            ".cif,.xyz,.poscar,.cell,.pdb,.dat,.txt,.xls,.xlsx",
        )
    )
}
THREEDGS_MCP_ENABLED = (os.getenv("THREEDGS_MCP_ENABLED", "true") or "true").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}
THREEDGS_MCP_SERVER_URL = os.getenv("THREEDGS_MCP_SERVER_URL", "http://127.0.0.1:8090/mcp")
THREEDGS_MCP_API_KEY = os.getenv("THREEDGS_MCP_API_KEY", "")
THREEDGS_PUBLIC_BASE_URL = _validate_3dgs_public_base_url(
    APP_ENV,
    os.getenv("THREEDGS_PUBLIC_BASE_URL"),
)
THREEDGS_RENDER_TTL_SEC = int(os.getenv("THREEDGS_RENDER_TTL_SEC", "600"))
THREEDGS_SESSION_FILE = SPLAT_PIPELINE_DIR / "3dgs_sessions.json"


def _resolve_spark_root() -> Path:
    configured = (os.getenv("SPARK_ROOT") or "").strip()
    if configured:
        return Path(configured).expanduser()

    candidates = [
        Path("D:/tools/spark"),
        Path.home() / "tools" / "spark",
        Path.home() / "spark",
        BASE_DIR / "tools" / "vendor" / "spark",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate

    return candidates[0]


SPARK_ROOT = _resolve_spark_root()

CIF_DIR.mkdir(parents=True, exist_ok=True)
SPLAT_DIR.mkdir(parents=True, exist_ok=True)
SPLAT_SOURCE_DIR.mkdir(parents=True, exist_ok=True)
SPLAT_DERIVED_DIR.mkdir(parents=True, exist_ok=True)
SPLAT_PIPELINE_DIR.mkdir(parents=True, exist_ok=True)
METRICS_DIR.mkdir(parents=True, exist_ok=True)
METRICS_RAW_DIR.mkdir(parents=True, exist_ok=True)
MCP_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

MP_API_KEY = os.getenv("MP_API_KEY") or os.getenv("MAPI_KEY")
POE_API_KEY = os.getenv("POE_API_KEY")
POE_API_BASE_URL = os.getenv("POE_API_BASE_URL", "https://api.poe.com/v1")

# DeepSeek via uni-api (overrides POE aliases above when using direct import)
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", POE_API_KEY or "")
DEEPSEEK_API_BASE_URL = os.getenv("DEEPSEEK_API_BASE_URL", "https://uni-api.cstcloud.cn/v1")
DEEPSEEK_MODEL_ID = os.getenv("DEEPSEEK_MODEL_ID", "deepseek-v4-flash")

LLM_MODEL_ID = os.getenv("LLM_MODEL_ID", "deepseek-v4-flash")
LLM_TIMEOUT_SEC = int(os.getenv("LLM_TIMEOUT_SEC", "45"))
