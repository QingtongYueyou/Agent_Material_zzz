from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parents[1]

load_dotenv(dotenv_path=BASE_DIR / ".env")

CIF_DIR = BASE_DIR / "cif_files"
STATIC_DIR = BASE_DIR / "static"
SPLAT_DIR = STATIC_DIR / "splat_files"

CIF_DIR.mkdir(parents=True, exist_ok=True)
SPLAT_DIR.mkdir(parents=True, exist_ok=True)

MP_API_KEY = os.getenv("MP_API_KEY") or os.getenv("MAPI_KEY")
POE_API_KEY = os.getenv("POE_API_KEY")
POE_API_BASE_URL = os.getenv("POE_API_BASE_URL", "https://api.poe.com/v1")
