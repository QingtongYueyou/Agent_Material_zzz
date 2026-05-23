from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parents[1]

load_dotenv(dotenv_path=BASE_DIR / ".env")

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

MP_API_KEY = os.getenv("MP_API_KEY") or os.getenv("MAPI_KEY")
POE_API_KEY = os.getenv("POE_API_KEY")
POE_API_BASE_URL = os.getenv("POE_API_BASE_URL", "https://api.poe.com/v1")

LLM_MODEL_ID = os.getenv("LLM_MODEL_ID", "GPT-4o")
LLM_TIMEOUT_SEC = int(os.getenv("LLM_TIMEOUT_SEC", "45"))
PLAN_API_TOKEN = os.getenv("PLAN_API_TOKEN", "")
