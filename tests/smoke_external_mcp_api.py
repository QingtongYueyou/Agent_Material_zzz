"""End-to-end smoke test for all non-CIF external visualization MCP routes."""

from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path

import httpx


DOWNLOAD_BASE = "http://219.232.220.140/dynamics/common/download?fileName="

# intent: (filename, download query, expected provider, expected tool)
SAMPLES = {
    "dos": ("dos.txt", "%2F124%2Fdataset%2F2026%2F05%2F07%2Fldos%20copy_1778134925101.txt&delete=false", "dos-mcp-server", "dos.dos_file"),
    "xrd": ("xrd.txt", "%2F124%2Fdataset%2F2026%2F05%2F07%2Fx-x%E5%B0%84%E7%BA%BF%E5%9B%BE_1778135162927.txt&delete=false", "x-ray-mcp-server", "x_ray.xrd_file"),
    "binary_phase": ("binary-phase.xls", "%2F124%2Fdataset%2F2026%2F05%2F07%2FFe-c_1778135093379.xls&delete=false", "hot2-mcp-server", "hot2.binary_xlsx_file"),
    "ternary_phase": ("ternary-phase.xls", "%2F124%2Fdataset%2F2026%2F05%2F07%2FAl-Si-Mg_1778135115091.xls&delete=false", "hot3-mcp-server", "hot3.ternary_xlsx_file"),
    "band": ("band.zip", "%2F124%2Fdataset%2F2026%2F05%2F07%2Ftest1_1778135138506.zip&delete=false", "nb-mcp-server", "nb.band_zip_file"),
    "vtp": ("model.vtp", "%2F124%2Fdataset%2F2026%2F05%2F29%2F1-1_1780041890666.vtp&delete=false", "yxy-mcp-server", "yxy.vtp_file"),
    "model": ("model.stl", "%2F124%2Fdataset%2F2026%2F05%2F07%2F20250919output1_1778135057041.stl&delete=false", "hj-ol-mcp-server", "hj_ol.model_file"),
    "molecular_dynamics": ("molecular-dynamics.dump", "%2F124%2Fdataset%2F2026%2F05%2F07%2FSi_melt_1778135027248.dump&delete=false", "fzdl-mcp-server", "fzdl.model_file"),
    "phase_curve": ("phase-curve.dat", "%2F124%2Fdataset%2F2026%2F05%2F07%2FMgZnCu-ternary_1778135187524.dat&delete=false", "xt-mcp-server", "xt.phase_curve_file"),
    "liquidus": ("liquidus.xlsx", "%2F124%2Fdataset%2F2026%2F05%2F07%2FAG-AL-CU-yexiangmiantouying_1778135213605.xlsx&delete=false", "yxty3-mcp-server", "yxty3.liquidus_xlsx_file"),
    "liquidus_dual": ("liquidus.xlsx", "%2F124%2Fdataset%2F2026%2F05%2F07%2FAG-AL-CU-yexiangmiantouying_1778135213605.xlsx&delete=false", "yxty3-mcp-server", "yxty3.liquidus_xlsx_file_dual"),
    "liquidus_mass": ("liquidus.xlsx", "%2F124%2Fdataset%2F2026%2F05%2F07%2FAG-AL-CU-yexiangmiantouying_1778135213605.xlsx&delete=false", "yxty3-mcp-server", "yxty3.liquidus_xlsx_file_mass"),
    "isothermal": ("isothermal.xlsx", "%2F124%2Fdataset%2F2026%2F05%2F07%2F2D_AG-AL-CU_symbol-sanyuandengwenjiemian_300K_Default_1778134951105.xlsx&delete=false", "dw3-mcp-server", "dw3.isothermal_xlsx_file"),
    "isothermal_dual": ("isothermal.xlsx", "%2F124%2Fdataset%2F2026%2F05%2F07%2F2D_AG-AL-CU_symbol-sanyuandengwenjiemian_300K_Default_1778134951105.xlsx&delete=false", "dw3-mcp-server", "dw3.isothermal_xlsx_file_dual"),
    "isothermal_mass": ("isothermal.xlsx", "%2F124%2Fdataset%2F2026%2F05%2F07%2F2D_AG-AL-CU_symbol-sanyuandengwenjiemian_300K_Default_1778134951105.xlsx&delete=false", "dw3-mcp-server", "dw3.isothermal_xlsx_file_mass"),
    "vertical_section": ("vertical.xlsx", "%2F124%2Fdataset%2F2026%2F05%2F07%2F0.1AG-AL-CU-cuizhijiemian_1778134897794.xlsx&delete=false", "cz3-mcp-server", "cz3.vertical_xlsx_file"),
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-base", default="http://127.0.0.1:8081")
    parser.add_argument("--intent", action="append", choices=sorted(SAMPLES))
    parser.add_argument(
        "--sample-dir",
        type=Path,
        default=Path(tempfile.gettempdir()) / "agent-material-mcp-samples",
    )
    parser.add_argument("--download-only", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    intents = args.intent or list(SAMPLES)
    sample_dir = args.sample_dir.resolve()
    sample_dir.mkdir(parents=True, exist_ok=True)
    api_base = args.api_base.rstrip("/")
    upload_ids: dict[Path, str] = {}
    failures = 0

    with httpx.Client(timeout=120) as client:
        for intent in intents:
            filename, source, provider, tool = SAMPLES[intent]
            path = sample_dir / filename
            try:
                if not path.is_file() or not path.stat().st_size:
                    download = client.get(f"{DOWNLOAD_BASE}{source}")
                    download.raise_for_status()
                    path.write_bytes(download.content)
                if args.download_only:
                    print(f"DOWNLOADED {intent:<20} {path}")
                    continue

                file_id = upload_ids.get(path)
                if file_id is None:
                    with path.open("rb") as source_file:
                        upload = client.post(
                            f"{api_base}/api/files/upload",
                            files={"file": (path.name, source_file)},
                        )
                    upload.raise_for_status()
                    file_id = str(upload.json()["file_id"])
                    upload_ids[path] = file_id

                response = client.post(
                    f"{api_base}/api/visualizations/render",
                    json={"intent": intent, "input_type": "file", "file_id": file_id},
                )
                response.raise_for_status()
                result = response.json()
                if not result.get("ok") or not result.get("render_url"):
                    raise RuntimeError("response is missing ok=true or render_url")
                if result.get("provider") != provider or result.get("tool") != tool:
                    raise RuntimeError(
                        f"unexpected route: {result.get('provider')!r} / {result.get('tool')!r}"
                    )
                print(f"PASS       {intent:<20} {provider} / {tool}")
            except Exception as exc:
                failures += 1
                print(f"FAIL       {intent:<20} {exc}", file=sys.stderr)

    print(f"\nSample directory: {sample_dir}")
    if not args.download_only:
        print(f"Result: {len(intents) - failures}/{len(intents)} routes passed")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
