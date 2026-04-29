from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parents[1]

load_dotenv(dotenv_path=BASE_DIR / ".env")

CIF_DIR = BASE_DIR / "cif_files"
STATIC_DIR = BASE_DIR / "static"
SPLAT_DIR = STATIC_DIR / "splat_files"
METRICS_DIR = BASE_DIR / "metrics"
METRICS_RAW_DIR = METRICS_DIR / "raw"
RENDER_METRICS_FILE = METRICS_RAW_DIR / "render_metrics.csv"
INTERACTION_METRICS_FILE = METRICS_RAW_DIR / "interaction_metrics.csv"
SPARK_ROOT = Path(os.getenv("SPARK_ROOT", str(BASE_DIR / "tools" / "vendor" / "spark")))
SPARK_STATUS_FILE = SPLAT_DIR / ".spark_asset_pipeline_status.json"
SPARK_AUTO_VARIANT = (os.getenv("SPARK_AUTO_VARIANT", "balanced") or "balanced").strip().lower()
SPARK_AUTO_INGEST = (os.getenv("SPARK_AUTO_INGEST", "true") or "true").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}

CIF_DIR.mkdir(parents=True, exist_ok=True)
SPLAT_DIR.mkdir(parents=True, exist_ok=True)
METRICS_DIR.mkdir(parents=True, exist_ok=True)
METRICS_RAW_DIR.mkdir(parents=True, exist_ok=True)

MP_API_KEY = os.getenv("MP_API_KEY") or os.getenv("MAPI_KEY")
POE_API_KEY = os.getenv("POE_API_KEY")
POE_API_BASE_URL = os.getenv("POE_API_BASE_URL", "https://api.poe.com/v1")

LLM_MODEL_ID = os.getenv("LLM_MODEL_ID", "GPT-4o")
LLM_TIMEOUT_SEC = int(os.getenv("LLM_TIMEOUT_SEC", "45"))
PLAN_API_TOKEN = os.getenv("PLAN_API_TOKEN", "")
