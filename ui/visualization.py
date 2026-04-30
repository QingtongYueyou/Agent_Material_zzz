from __future__ import annotations

import json
import logging
import os
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import altair as alt
import streamlit as st
import streamlit.components.v1 as components

from config.settings import BASE_DIR, SPLAT_DERIVED_DIR, SPLAT_DIR, SPLAT_SOURCE_DIR
from core.perf_metrics import (
    append_interaction_metric,
    append_render_metric,
    get_ply_bounds,
    get_ply_vertex_count,
)
from core.processor import HAS_PYMATGEN
from core.spark_asset_ingest import get_auto_ingest_status


logger = logging.getLogger(__name__)


class _CORSRequestHandler(SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(204)
        self.end_headers()

    def do_POST(self):
        if self.path not in {"/__perf/render-metrics", "/__perf/interaction-metrics"}:
            self.send_error(404, "Not Found")
            return

        content_length = int(self.headers.get("Content-Length", "0") or 0)
        payload = self.rfile.read(content_length) if content_length > 0 else b"{}"

        try:
            data = json.loads(payload.decode("utf-8"))
            if not isinstance(data, dict):
                raise ValueError("Payload must be a JSON object")

            if self.path == "/__perf/render-metrics":
                append_render_metric(data)
            else:
                append_interaction_metric(data)
        except Exception as exc:
            self.send_response(400)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps({"ok": False, "error": str(exc)}).encode("utf-8"))
            return

        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.end_headers()
        self.wfile.write(b'{"ok": true}')


@st.cache_resource
def _ensure_static_server(root_dir: str, port: int = 8001) -> int:
    handler = partial(_CORSRequestHandler, directory=root_dir)
    httpd = ThreadingHTTPServer(("127.0.0.1", port), handler)
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    return port


def _candidate_asset_keys(filename: str) -> list[str]:
    stem = Path(filename).stem
    parts = stem.split("_", 1)
    material_name = parts[0]
    formula_name = parts[1] if len(parts) > 1 else ""

    keys = [stem, material_name]
    if formula_name:
        keys.append(formula_name)
    keys.append("object")

    deduped: list[str] = []
    for key in keys:
        if key and key not in deduped:
            deduped.append(key)
    return deduped


def _safe_relative_to_base(path: Path) -> str | None:
    try:
        return path.resolve().relative_to(BASE_DIR.resolve()).as_posix()
    except ValueError:
        return None


def _manifest_candidates(asset_id: str) -> list[Path]:
    return [
        SPLAT_DERIVED_DIR / asset_id / f"{asset_id}.manifest.json",
        SPLAT_DIR / f"{asset_id}.manifest.json",
    ]


def _direct_asset_roots() -> list[Path]:
    roots = [SPLAT_SOURCE_DIR, SPLAT_DERIVED_DIR, SPLAT_DIR]
    deduped: list[Path] = []
    for root in roots:
        if root not in deduped:
            deduped.append(root)
    return deduped


def _resolve_asset_path(raw_path: str, manifest_path: Path | None = None) -> Path | None:
    candidate = Path(raw_path)
    search_roots = []

    if candidate.is_absolute():
        search_roots.append(candidate)
    else:
        if manifest_path is not None:
            search_roots.append((manifest_path.parent / candidate).resolve())
        search_roots.append((SPLAT_SOURCE_DIR / candidate).resolve())
        search_roots.append((SPLAT_DERIVED_DIR / candidate).resolve())
        search_roots.append((SPLAT_DIR / candidate).resolve())
        search_roots.append((BASE_DIR / candidate).resolve())

    for path in search_roots:
        if path.exists() and _safe_relative_to_base(path) is not None:
            return path
    return None


def _read_manifest(path: Path) -> dict[str, Any] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None

    if isinstance(data, dict):
        return data
    return None


def _build_asset_record(
    path: Path,
    *,
    asset_id: str,
    variant_name: str,
    source_kind: str,
    manifest_name: str | None,
    selection_note: str,
    enable_lod: bool | None = None,
    enable_paged: bool | None = None,
) -> dict[str, Any] | None:
    url_path = _safe_relative_to_base(path)
    if url_path is None:
        return None

    model_format = path.suffix.lstrip(".").lower()
    vertex_count = get_ply_vertex_count(path)
    file_size_bytes = path.stat().st_size
    is_large_model = (
        file_size_bytes >= 100 * 1024 * 1024
        or (vertex_count is not None and vertex_count >= 1_000_000)
    )

    if enable_lod is None:
        enable_lod = is_large_model and model_format != "rad"
    if enable_paged is None:
        enable_paged = model_format == "rad"

    if model_format == "rad":
        lod_mode_label = "RAD paged LoD" if enable_paged else "RAD prebuilt LoD"
    elif enable_lod:
        lod_mode_label = "dynamic LoD"
    else:
        lod_mode_label = "full detail"

    return {
        "asset_id": asset_id,
        "variant_name": variant_name,
        "source_kind": source_kind,
        "manifest_name": manifest_name or "",
        "selection_note": selection_note,
        "path": path,
        "url_path": url_path,
        "model_name": path.name,
        "model_format": model_format,
        "vertex_count": vertex_count,
        "vertex_count_label": "未知" if vertex_count is None else str(vertex_count),
        "file_size_bytes": file_size_bytes,
        "file_mtime": int(path.stat().st_mtime),
        "is_large_model": is_large_model,
        "enable_lod": enable_lod,
        "enable_paged": enable_paged,
        "lod_mode_label": lod_mode_label,
    }


def _select_manifest_asset(manifest_path: Path, quality_preference: str) -> dict[str, Any] | None:
    manifest = _read_manifest(manifest_path)
    if not manifest:
        return None

    asset_id = str(manifest.get("asset_id") or manifest_path.name.replace(".manifest.json", ""))
    raw_variants = manifest.get("variants")
    variants = raw_variants if isinstance(raw_variants, dict) else {}

    requested_quality = quality_preference if quality_preference != "auto" else ""
    selection_order: list[str] = []

    if requested_quality:
        selection_order.append(requested_quality)

    default_variant = str(manifest.get("default_variant") or "").strip()
    for name in [default_variant, "balanced", "preview", "full", "source"]:
        if name and name not in selection_order:
            selection_order.append(name)

    for variant_name, payload in variants.items():
        if isinstance(variant_name, str) and variant_name not in selection_order:
            selection_order.append(variant_name)

    for variant_name in selection_order:
        payload = variants.get(variant_name)
        if not isinstance(payload, dict):
            continue

        raw_path = payload.get("path") or payload.get("file") or payload.get("relative_path")
        if not isinstance(raw_path, str) or not raw_path.strip():
            continue

        resolved_path = _resolve_asset_path(raw_path, manifest_path)
        if resolved_path is None:
            continue

        if requested_quality and variant_name != requested_quality:
            selection_note = (
                f"Requested quality '{requested_quality}' unavailable; using '{variant_name}'"
            )
        else:
            selection_note = f"Manifest '{manifest_path.name}' -> variant '{variant_name}'"

        asset_record = _build_asset_record(
            resolved_path,
            asset_id=asset_id,
            variant_name=variant_name,
            source_kind="manifest",
            manifest_name=manifest_path.name,
            selection_note=selection_note,
            enable_lod=bool(payload.get("lod")) if "lod" in payload else None,
            enable_paged=bool(payload.get("paged")) if "paged" in payload else None,
        )
        if asset_record is None:
            continue

        raw_source_path = payload.get("source_path")
        if not isinstance(raw_source_path, str) or not raw_source_path.strip():
            source_payload = variants.get("source")
            if isinstance(source_payload, dict):
                source_candidate = source_payload.get("path") or source_payload.get("file")
                raw_source_path = source_candidate if isinstance(source_candidate, str) else ""

        if raw_source_path:
            source_path = _resolve_asset_path(raw_source_path, manifest_path)
            if source_path is not None:
                asset_record["view_bounds"] = get_ply_bounds(source_path)

        return asset_record

    return None


def _resolve_direct_asset(filename: str) -> dict[str, Any] | None:
    keys = _candidate_asset_keys(filename)
    suffixes = [".rad", ".ply", ".spz", ".splat", ".ksplat"]

    for key in keys:
        exact_candidates: list[Path] = []
        for root in _direct_asset_roots():
            exact_candidates.append(root / f"{key}-lod.rad")
            exact_candidates.extend(root / f"{key}{suffix}" for suffix in suffixes)

        for candidate in exact_candidates:
            if not candidate.exists():
                continue

            note = (
                f"No manifest found; using fallback asset '{candidate.name}'"
                if key == "object"
                else f"No manifest found; using direct asset '{candidate.name}'"
            )
            return _build_asset_record(
                candidate,
                asset_id=Path(filename).stem,
                variant_name="direct",
                source_kind="direct",
                manifest_name=None,
                selection_note=note,
            )

        for root in _direct_asset_roots():
            for pattern in (f"*{key}*-lod.rad", f"*{key}*.rad", f"*{key}*.ply"):
                matches = sorted(root.rglob(pattern))
                if not matches:
                    continue

                return _build_asset_record(
                    matches[0],
                    asset_id=Path(filename).stem,
                    variant_name="direct",
                    source_kind="direct",
                    manifest_name=None,
                    selection_note=f"No manifest found; using glob match '{matches[0].name}'",
                )

    return None


def _resolve_splat_asset(filename: str, quality_preference: str) -> dict[str, Any] | None:
    for key in _candidate_asset_keys(filename):
        for manifest_path in _manifest_candidates(key):
            if not manifest_path.exists():
                continue

            asset_record = _select_manifest_asset(manifest_path, quality_preference)
            if asset_record is not None:
                return asset_record

    return _resolve_direct_asset(filename)


def _render_asset_pipeline_status() -> None:
    status = get_auto_ingest_status()
    if not status.get("enabled"):
        return

    pending_count = int(status.get("pending_count") or 0)
    variant = str(status.get("variant") or "balanced")
    spark_root_exists = bool(status.get("spark_root_exists"))
    active_asset = str(status.get("active_asset") or "")

    if bool(status.get("running")):
        label = active_asset or f"{pending_count} asset(s)"
        st.info(f"3D 资产后台处理中：`{label}`，目标档位 `{variant}`。")
        return

    if pending_count > 0:
        if spark_root_exists:
            st.info(f"检测到 {pending_count} 个新/变更模型，后台会自动生成 `{variant}` 资产。")
        else:
            st.warning(
                f"检测到 {pending_count} 个新/变更模型，但 Spark 工具目录不可用，只会注册 source，不会自动构建 `{variant}`。"
            )
        return

    summary = status.get("summary")
    if isinstance(summary, dict) and int(summary.get("errors", 0) or 0) > 0:
        error_count = int(summary.get("errors", 0) or 0)
        logger.info(
            "Last 3D asset auto-build completed with %s error(s); hidden from UI.",
            error_count,
        )
        return

    if isinstance(summary, dict) and int(summary.get("built", 0) or 0) > 0:
        built_count = int(summary.get("built", 0) or 0)
        st.caption(f"3D 资产自动管线已就绪，最近一次后台构建完成 {built_count} 个 `{variant}` 资产。")


_TEMPLATE_PATH = Path(__file__).resolve().parent / "spark_viewer_template.html"
_LEGACY_SPLAT_DIRS = [SPLAT_SOURCE_DIR, SPLAT_DERIVED_DIR, SPLAT_DIR]


def _build_spark_viewer_html(
    *,
    asset_id: str,
    model_url: str,
    model_name: str,
    model_format: str,
    variant_name: str,
    vertex_count: int | None,
    vertex_count_label: str,
    file_size_bytes: int,
    is_large_model: bool,
    enable_lod: bool,
    enable_paged: bool,
    lod_mode_label: str,
    metrics_url: str,
    interaction_metrics_url: str,
    view_bounds: dict[str, Any] | None = None,
) -> str:
    if not _TEMPLATE_PATH.exists():
        return """
        <!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="utf-8">
            <style>
                body {
                    margin: 0;
                    font-family: "Segoe UI", Arial, sans-serif;
                    background: #f8fafc;
                }
                .spark-template-error {
                    height: 350px;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    padding: 24px;
                    color: #991b1b;
                    background: #fef2f2;
                    border: 1px solid #fecaca;
                    border-radius: 16px;
                    text-align: center;
                }
            </style>
        </head>
        <body>
            <div class="spark-template-error">
                Missing Spark viewer template: ui/spark_viewer_template.html
            </div>
        </body>
        </html>
        """

    template = _TEMPLATE_PATH.read_text(encoding="utf-8")
    variant_name_or_default = variant_name if variant_name else "default"

    replacements = [
        ("__ASSET_ID_JSON__", json.dumps(asset_id)),
        ("__ASSET_ID__", asset_id),
        ("__MODEL_URL__", model_url),
        ("__MODEL_NAME__", model_name),
        ("__MODEL_FORMAT__", model_format),
        ("__VARIANT_NAME_OR_DEFAULT__", variant_name_or_default),
        ("__VARIANT_NAME_JSON__", json.dumps(variant_name)),
        ("__VERTEX_COUNT_LABEL__", vertex_count_label),
        ("__VERTEX_COUNT_JSON__", json.dumps(vertex_count)),
        ("__FILE_SIZE_BYTES__", str(file_size_bytes)),
        ("__LARGE_MODEL_JSON__", json.dumps(is_large_model)),
        ("__ENABLE_LOD_JSON__", json.dumps(enable_lod)),
        ("__ENABLE_PAGED_JSON__", json.dumps(enable_paged)),
        ("__LOD_MODE_LABEL_JSON__", json.dumps(lod_mode_label)),
        ("__VIEW_BOUNDS_JSON__", json.dumps(view_bounds)),
        ("__METRICS_URL__", metrics_url),
        ("__INTERACTION_METRICS_URL__", interaction_metrics_url),
    ]

    html = template
    for placeholder, value in replacements:
        html = html.replace(placeholder, value)

    return html


def render_visualization_panel() -> None:
    st.markdown(
        """
        <div style="display: flex; align-items: center; gap: 0.6rem; margin-bottom: 0.8rem;">
            <span class="section-label label-b">B</span>
            <span style="font-size: 1rem; font-weight: 700; color: #1a202c;">可视化探索</span>
        </div>
        <div style="font-size: 0.8rem; color: #64748b; margin-bottom: 1rem;">
            📊 结构数据视图 · <span class="badge badge-blue">动态生成</span>
        </div>
        """,
        unsafe_allow_html=True,
    )

    _render_asset_pipeline_status()
    if not HAS_PYMATGEN:
        st.error("⚠️ 未检测到 `pymatgen` 库。可视化功能受限。请运行 `pip install pymatgen`。")

    if st.session_state.viz_data is None:
        if st.session_state.messages:
            st.info("💡 请在左侧输入材料名称（如 LiFePO4），AI 将获取结构并在此生成分析图表。")
            st.markdown(
                """
                <div class="card" style="height: 200px; display: flex; align-items: center; justify-content: center; color: #cbd5e0;">
                    等待数据输入...
                </div>
                """,
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                """
                <div class="card" style="height: 200px;"></div>
                """,
                unsafe_allow_html=True,
            )
        return

    viz = st.session_state.viz_data
    filename = viz["filename"]

    quality_options = ["auto", "preview", "balanced", "full", "source"]
    quality_labels = {
        "auto": "Auto",
        "preview": "Preview",
        "balanced": "Balanced",
        "full": "Full",
        "source": "Source",
    }
    title_col, quality_select_col = st.columns([0.68, 0.32], gap="small")
    with title_col:
        st.markdown(
            """
            <div class="viewer-toolbar-title">
                <span class="viewer-toolbar-index">1</span>
                <span>3D Gaussian Splatting 视图 (WebGL)</span>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with quality_select_col:
        st.selectbox(
            "3D Asset Quality",
            options=quality_options,
            format_func=lambda option: quality_labels[option],
            key="splat_quality",
            help="When a manifest exists, choose which prebuilt asset variant to load.",
            label_visibility="collapsed",
        )
    asset_info = _resolve_splat_asset(filename, st.session_state.get("splat_quality", "auto"))

    cif_basename = os.path.splitext(filename)[0]
    parts = cif_basename.split("_", 1)
    material_name = parts[0]
    formula_name = parts[1] if len(parts) > 1 else ""

    search_candidates: list[str] = []
    for root in _LEGACY_SPLAT_DIRS:
        search_candidates.extend(
            [
                os.path.join(root, f"{cif_basename}-lod.rad"),
                os.path.join(root, f"{cif_basename}.rad"),
                os.path.join(root, f"{cif_basename}.ply"),
                os.path.join(root, f"{cif_basename}.spz"),
                os.path.join(root, f"{cif_basename}.splat"),
                os.path.join(root, f"{material_name}-lod.rad"),
                os.path.join(root, f"{material_name}.rad"),
                os.path.join(root, f"{material_name}.ply"),
                os.path.join(root, f"{material_name}.spz"),
                os.path.join(root, f"{material_name}.splat"),
                os.path.join(root, f"{formula_name}-lod.rad") if formula_name else "",
                os.path.join(root, f"{formula_name}.rad") if formula_name else "",
                os.path.join(root, f"{formula_name}.ply") if formula_name else "",
                os.path.join(root, f"{formula_name}.spz") if formula_name else "",
                os.path.join(root, f"{formula_name}.splat") if formula_name else "",
                f"GLOB:{os.path.join(root, f'*{formula_name}*-lod.rad')}" if formula_name else "",
                f"GLOB:{os.path.join(root, f'*{formula_name}*.rad')}" if formula_name else "",
                f"GLOB:{os.path.join(root, f'*{formula_name}*.ply')}" if formula_name else "",
                f"GLOB:{os.path.join(root, f'*{material_name}*-lod.rad')}",
                f"GLOB:{os.path.join(root, f'*{material_name}*.rad')}",
                f"GLOB:{os.path.join(root, f'*{material_name}*.ply')}",
                os.path.join(root, "object-lod.rad"),
                os.path.join(root, "object.rad"),
                os.path.join(root, "object.ply"),
            ]
        )

    found_splat_path = None if asset_info is None else str(asset_info["path"])

    if asset_info is None:
        for candidate in search_candidates:
            if not candidate:
                continue
            if candidate.startswith("GLOB:"):
                import glob

                matches = glob.glob(candidate.replace("GLOB:", ""))
                if matches:
                    found_splat_path = matches[0]
                    break
            elif os.path.exists(candidate):
                found_splat_path = candidate
                break

    if found_splat_path:
        if asset_info is not None:
            file_name_only = str(asset_info["model_name"])
            file_ext = f".{asset_info['model_format']}"
            vertex_count = asset_info["vertex_count"]
        else:
            file_name_only = os.path.basename(found_splat_path)
            file_ext = os.path.splitext(file_name_only)[1].lower()
            vertex_count = get_ply_vertex_count(found_splat_path)
        vertex_count_label = "未知" if vertex_count is None else str(vertex_count)
        file_size_bytes = os.path.getsize(found_splat_path)
        file_mtime = int(os.path.getmtime(found_splat_path))
        is_large_model = (
            file_size_bytes >= 100 * 1024 * 1024
            or (vertex_count is not None and vertex_count >= 1_000_000)
        )
        asset_id = os.path.splitext(filename)[0]
        variant_name = "direct"
        enable_lod = is_large_model and file_ext != ".rad"
        enable_paged = file_ext == ".rad"
        lod_mode_label = (
            "RAD paged LoD"
            if enable_paged
            else ("dynamic LoD" if enable_lod else "full detail")
        )

        if asset_info is not None:
            vertex_count_label = str(asset_info["vertex_count_label"])
            file_size_bytes = int(asset_info["file_size_bytes"])
            file_mtime = int(asset_info["file_mtime"])
            is_large_model = bool(asset_info["is_large_model"])
            asset_id = str(asset_info["asset_id"])
            variant_name = str(asset_info["variant_name"])
            enable_lod = bool(asset_info["enable_lod"])
            enable_paged = bool(asset_info["enable_paged"])
            lod_mode_label = str(asset_info["lod_mode_label"])

        port = _ensure_static_server(str(BASE_DIR), port=8001)
        if asset_info is not None:
            model_url = f"http://127.0.0.1:{port}/{asset_info['url_path']}?v={file_mtime}"
        else:
            model_url = f"http://127.0.0.1:{port}/static/splat_files/{file_name_only}?v={file_mtime}"
        metrics_url = f"http://127.0.0.1:{port}/__perf/render-metrics"
        interaction_metrics_url = f"http://127.0.0.1:{port}/__perf/interaction-metrics"

        if asset_info is None and file_name_only == "object.ply":
            st.caption(f"ℹ️ 未找到专属模型，展示测试文件: `{file_name_only}`")
        elif asset_info is None:
            st.caption(f"✅ 已加载模型: `{file_name_only}`")

        # Keep the previous viewer template inert so the Spark rollout stays localized.
        _legacy_gs_html = None and f"""
                    <!DOCTYPE html>
                    <html lang="en">
                    <head>
                        <meta charset="utf-8">
                        <meta name="viewport" content="width=device-width, initial-scale=1.0">
                        <style>
                            body {{ margin: 0; overflow: hidden; background: #fff; font-family: sans-serif; }}
                            #container {{ width: 100%; height: 350px; }}

                            #fps-display {{
                                position: absolute;
                                top: 10px;
                                right: 10px;
                                background: rgba(0, 0, 0, 0.6);
                                color: #4ade80;
                                padding: 4px 8px;
                                border-radius: 6px;
                                font-size: 12px;
                                font-weight: 700;
                                pointer-events: none;
                                z-index: 100;
                                backdrop-filter: blur(2px);
                                border: 1px solid rgba(255,255,255,0.1);
                                font-family: monospace;
                            }}

                            #perf-panel {{
                                position: absolute;
                                left: 10px;
                                top: 10px;
                                z-index: 101;
                                display: flex;
                                flex-direction: column;
                                gap: 8px;
                                max-width: 240px;
                            }}

                            #perf-button {{
                                border: none;
                                border-radius: 6px;
                                background: rgba(15, 23, 42, 0.86);
                                color: white;
                                padding: 8px 10px;
                                font-size: 12px;
                                cursor: pointer;
                            }}

                            #perf-button:hover {{
                                background: rgba(30, 41, 59, 0.92);
                            }}

                            #perf-summary {{
                                background: rgba(255, 255, 255, 0.92);
                                color: #0f172a;
                                border-radius: 8px;
                                padding: 8px 10px;
                                font-size: 12px;
                                line-height: 1.45;
                                box-shadow: 0 2px 8px rgba(15, 23, 42, 0.15);
                            }}

                            #perf-toggle {{
                                border: none;
                                border-radius: 6px;
                                background: rgba(255, 255, 255, 0.92);
                                color: #0f172a;
                                padding: 8px 10px;
                                font-size: 12px;
                                cursor: pointer;
                                box-shadow: 0 2px 8px rgba(15, 23, 42, 0.15);
                                text-align: left;
                            }}

                            #perf-tools {{
                                display: none;
                                flex-direction: column;
                                gap: 8px;
                            }}

                            #perf-tools.visible {{
                                display: flex;
                            }}
                        </style>
                        <script type="importmap">
                        {{
                            "imports": {{
                                "three": "https://cdn.jsdelivr.net/npm/three@0.157.0/build/three.module.js",
                                "@mkkellogg/gaussian-splats-3d": "https://cdn.jsdelivr.net/npm/@mkkellogg/gaussian-splats-3d@0.4.7/build/gaussian-splats-3d.module.js"
                            }}
                        }}
                        </script>
                    </head>
                    <body>
                        <div id="container"></div>
                        <div id="perf-panel">
                            <button id="perf-toggle" type="button">显示测试面板</button>
                            <div id="perf-tools">
                                <button id="perf-button" type="button">测试渲染</button>
                                <div id="perf-summary">
                                    模型: {file_name_only}<br/>
                                    顶点数: {vertex_count_label}<br/>
                                    打开测试面板后可记录渲染和交互延迟
                                </div>
                            </div>
                        </div>

                        <div id="loading" style="position:absolute; top:50%; left:50%; transform:translate(-50%, -50%); background:rgba(0,0,0,0.7); color:white; padding:10px 20px; border-radius:8px; font-size:14px; display:flex; align-items:center; gap:10px;">
                            <div style="width:16px; height:16px; border:2px solid white; border-top-color:transparent; border-radius:50%; animation:spin 1s linear infinite;"></div>
                            <div id="progress-text">Loading...</div>
                        </div>

                        <div id="fps-display">FPS: --</div>

                        <style>@keyframes spin {{ to {{ transform: rotate(360deg); }} }}</style>

                        <script type="module">
                            import * as GaussianSplats3D from '@mkkellogg/gaussian-splats-3d';

                            const container = document.getElementById('container');
                            const loadingLabel = document.getElementById('loading');
                            const fpsDiv = document.getElementById('fps-display');
                            const progressText = document.getElementById('progress-text');
                            const perfToggle = document.getElementById('perf-toggle');
                            const perfTools = document.getElementById('perf-tools');
                            const perfButton = document.getElementById('perf-button');
                            const perfSummary = document.getElementById('perf-summary');

                            let fpsLoopStarted = false;
                            let runCounter = 0;
                            let interactionEnabled = false;
                            let pendingInteraction = null;

                            function updateSummary(lines) {{
                                perfSummary.innerHTML = lines.join('<br/>');
                            }}

                            function postMetrics(record) {{
                                fetch("{metrics_url}", {{
                                    method: "POST",
                                    headers: {{
                                        "Content-Type": "application/json"
                                    }},
                                    body: JSON.stringify(record),
                                    keepalive: true
                                }}).catch((err) => console.error("Metrics upload error:", err));
                            }}

                            function postInteractionMetrics(record) {{
                                fetch("{interaction_metrics_url}", {{
                                    method: "POST",
                                    headers: {{
                                        "Content-Type": "application/json"
                                    }},
                                    body: JSON.stringify(record),
                                    keepalive: true
                                }}).catch((err) => console.error("Interaction metrics upload error:", err));
                            }}

                            function cameraSnapshot(activeViewer) {{
                                const camera = activeViewer.camera;
                                if (!camera) {{
                                    return null;
                                }}

                                return {{
                                    position: [camera.position.x, camera.position.y, camera.position.z],
                                    quaternion: [camera.quaternion.x, camera.quaternion.y, camera.quaternion.z, camera.quaternion.w]
                                }};
                            }}

                            function hasCameraChanged(before, after) {{
                                if (!before || !after) {{
                                    return false;
                                }}

                                const valuesBefore = before.position.concat(before.quaternion);
                                const valuesAfter = after.position.concat(after.quaternion);

                                for (let i = 0; i < valuesBefore.length; i += 1) {{
                                    if (Math.abs(valuesBefore[i] - valuesAfter[i]) > 1e-4) {{
                                        return true;
                                    }}
                                }}

                                return false;
                            }}

                            function armInteractionMeasurement(activeViewer, interactionType, eventType) {{
                                if (!interactionEnabled) {{
                                    return;
                                }}

                                pendingInteraction = {{
                                    interactionType,
                                    eventType,
                                    startTs: performance.now(),
                                    baseline: cameraSnapshot(activeViewer),
                                    recorded: false
                                }};

                                updateSummary([
                                    `模型: {file_name_only}`,
                                    `顶点数: {vertex_count_label}`,
                                    `交互测试: ${{interactionType}}`,
                                    '状态: 等待相机发生变化...'
                                ]);
                            }}

                            function maybeRecordInteraction(activeViewer) {{
                                if (!pendingInteraction || pendingInteraction.recorded) {{
                                    return;
                                }}

                                const current = cameraSnapshot(activeViewer);
                                if (!hasCameraChanged(pendingInteraction.baseline, current)) {{
                                    return;
                                }}

                                const latencyMs = Number((performance.now() - pendingInteraction.startTs).toFixed(3));
                                pendingInteraction.recorded = true;

                                const metric = {{
                                    event_type: pendingInteraction.eventType,
                                    model_name: "{file_name_only}",
                                    model_format: "{file_ext.lstrip('.')}",
                                    vertex_count: {json.dumps(vertex_count)},
                                    file_size_bytes: {file_size_bytes},
                                    interaction_type: pendingInteraction.interactionType,
                                    input_to_camera_change_ms: latencyMs,
                                    viewport_width: window.innerWidth,
                                    viewport_height: window.innerHeight,
                                    user_agent: navigator.userAgent
                                }};

                                postInteractionMetrics(metric);
                                updateSummary([
                                    `模型: {file_name_only}`,
                                    `顶点数: {vertex_count_label}`,
                                    `交互: ${{pendingInteraction.interactionType}}`,
                                    `input->camera change: ${{latencyMs}} ms`
                                ]);
                            }}

                            function createViewer() {{
                                container.innerHTML = '';
                                return new GaussianSplats3D.Viewer({{
                                    'rootElement': container,
                                    'cameraUp': [0, 1, 0],
                                    'initialCameraPosition': [2, 2, 5],
                                    'initialCameraLookAt': [0, 0, 0],
                                    'selfDrivenMode': true,
                                    'useBuiltInControls': true,
                                    'sharedMemoryForWorkers': false,
                                    'gpuAcceleratedSort': false
                                }});
                            }}

                            function startFPSLoop() {{
                                if (fpsLoopStarted) {{
                                    return;
                                }}

                                fpsLoopStarted = true;
                                let frameCount = 0;
                                let lastTime = performance.now();

                                function updateFPS() {{
                                    const now = performance.now();
                                    frameCount++;
                                    if (window.__perfViewerRef) {{
                                        maybeRecordInteraction(window.__perfViewerRef);
                                    }}

                                    if (now - lastTime >= 500) {{
                                        const fps = Math.round((frameCount * 1000) / (now - lastTime));
                                        fpsDiv.innerText = `FPS: ${{fps}}`;

                                        if (fps >= 40) fpsDiv.style.color = '#4ade80';
                                        else if (fps >= 20) fpsDiv.style.color = '#facc15';
                                        else fpsDiv.style.color = '#f87171';

                                        frameCount = 0;
                                        lastTime = now;
                                    }}

                                    requestAnimationFrame(updateFPS);
                                }}

                                requestAnimationFrame(updateFPS);
                            }}

                            function loadScene(eventType) {{
                                const clickTs = performance.now();
                                const requestStartTs = performance.now();
                                runCounter += 1;
                                const runId = runCounter;
                                const activeViewer = createViewer();
                                window.__perfViewerRef = activeViewer;
                                pendingInteraction = null;

                                loadingLabel.style.display = 'flex';
                                loadingLabel.style.background = 'rgba(0,0,0,0.7)';
                                progressText.innerText = 'Loading...';
                                perfButton.disabled = true;

                                updateSummary([
                                    '模型: {file_name_only}',
                                    '顶点数: {vertex_count_label}',
                                    '状态: 测试中...'
                                ]);

                                activeViewer.addSplatScene("{model_url}", {{
                                    'format': {format_enum},
                                    'scale': [1, 1, 1],
                                    'splatAlphaRemovalThreshold': 5,
                                    'showLoadingUI': false
                                }})
                                .then(() => {{
                                    const sceneReadyTs = performance.now();
                                    activeViewer.start();
                                    loadingLabel.style.display = 'none';
                                    startFPSLoop();

                                    requestAnimationFrame(() => {{
                                        const firstFrameTs = performance.now();
                                        const metric = {{
                                            event_type: eventType,
                                            model_name: "{file_name_only}",
                                            model_format: "{file_ext.lstrip('.')}",
                                            vertex_count: {json.dumps(vertex_count)},
                                            file_size_bytes: {file_size_bytes},
                                            click_to_request_start_ms: Number((requestStartTs - clickTs).toFixed(3)),
                                            request_start_to_scene_ready_ms: Number((sceneReadyTs - requestStartTs).toFixed(3)),
                                            scene_ready_to_first_frame_ms: Number((firstFrameTs - sceneReadyTs).toFixed(3)),
                                            click_to_first_frame_ms: Number((firstFrameTs - clickTs).toFixed(3)),
                                            viewport_width: window.innerWidth,
                                            viewport_height: window.innerHeight,
                                            user_agent: navigator.userAgent
                                        }};

                                        postMetrics(metric);
                                        updateSummary([
                                            `模型: {file_name_only}`,
                                            `顶点数: {vertex_count_label}`,
                                            `事件: ${{eventType}} #${{runId}}`,
                                            `click->first frame: ${{metric.click_to_first_frame_ms}} ms`,
                                            `request->ready: ${{metric.request_start_to_scene_ready_ms}} ms`,
                                            `ready->frame: ${{metric.scene_ready_to_first_frame_ms}} ms`
                                        ]);
                                        perfButton.disabled = false;
                                    }});
                                }})
                                .catch((err) => {{
                                    console.error("Splat load error:", err);
                                    loadingLabel.style.display = 'flex';
                                    loadingLabel.style.background = "rgba(220, 38, 38, 0.9)";
                                    progressText.innerText = "Error: Check Console";
                                    updateSummary([
                                        '模型: {file_name_only}',
                                        '顶点数: {vertex_count_label}',
                                        '状态: 加载失败，请查看控制台'
                                    ]);
                                    perfButton.disabled = false;
                                }});
                            }}

                            perfToggle.addEventListener('click', () => {{
                                interactionEnabled = !interactionEnabled;
                                perfTools.classList.toggle('visible', interactionEnabled);
                                perfToggle.innerText = interactionEnabled ? '隐藏测试面板' : '显示测试面板';
                            }});
                            perfButton.addEventListener('click', () => loadScene('manual_retest'));
                            container.addEventListener('pointerdown', () => {{
                                if (window.__perfViewerRef) {{
                                    armInteractionMeasurement(window.__perfViewerRef, 'rotate_or_pan', 'pointerdown');
                                }}
                            }});
                            container.addEventListener('wheel', () => {{
                                if (window.__perfViewerRef) {{
                                    armInteractionMeasurement(window.__perfViewerRef, 'zoom', 'wheel');
                                }}
                            }}, {{ passive: true }});
                            loadScene('auto_initial');
                        </script>
                    </body>
                    </html>
                    """
        gs_html = _build_spark_viewer_html(
            asset_id=asset_id,
            model_url=model_url,
            model_name=file_name_only,
            model_format=file_ext.lstrip("."),
            variant_name=variant_name,
            vertex_count=vertex_count,
            vertex_count_label=vertex_count_label,
            file_size_bytes=file_size_bytes,
            is_large_model=is_large_model,
            enable_lod=enable_lod,
            enable_paged=enable_paged,
            lod_mode_label=lod_mode_label,
            metrics_url=metrics_url,
            interaction_metrics_url=interaction_metrics_url,
            view_bounds=asset_info.get("view_bounds") if asset_info is not None else None,
        )
        components.html(gs_html, height=350)
    else:
        st.warning("⚠️ 在 `static/splat_files` 中未找到匹配的模型文件。")
        st.markdown(f"<small>搜索路径: {SPLAT_DIR}</small>", unsafe_allow_html=True)

    viz_col1, viz_col2 = st.columns(2, gap="medium")

    with viz_col1:
        st.markdown(
            """
            <div class="chart-toolbar-title">
                <span class="chart-toolbar-index">2</span>
                <span>晶胞参数 (Lattice)</span>
            </div>
            """,
            unsafe_allow_html=True,
        )

        chart_lat = (
            alt.Chart(viz["lattice_df"])
            .mark_bar(color="#667eea", cornerRadiusTopLeft=6, cornerRadiusTopRight=6)
            .encode(
                x=alt.X(
                    "Parameter:N",
                    title=None,
                    axis=alt.Axis(labelAngle=0, labelFontSize=11, labelFontWeight="bold"),
                ),
                y=alt.Y("Value:Q", title="长度 (Å)", axis=alt.Axis(labelFontSize=10)),
                color=alt.Color(
                    "Parameter", legend=None, scale=alt.Scale(scheme="tableau10")
                ),
                tooltip=["Parameter", "Value", "Unit"],
            )
            .properties(height=180)
            .configure_axis(gridColor="#f1f5f9", domainColor="#cbd5e0")
            .configure_view(strokeWidth=0)
        )

        st.altair_chart(chart_lat, use_container_width=True)

        max_axis = viz["lattice_df"].loc[viz["lattice_df"]["Value"].idxmax()]

        st.markdown(
            f"""
            <div class="finding-box">
                <div class="finding-title">🔍 结构特征</div>
                <div class="finding-text">
                    当前晶胞中最长的轴为 <span class="highlight">{max_axis['Parameter']} 轴</span>
                    ({max_axis['Value']:.2f} Å)。
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with viz_col2:
        st.markdown(
            """
            <div class="chart-toolbar-title">
                <span class="chart-toolbar-index">3</span>
                <span>化学组分 (Composition)</span>
            </div>
            """,
            unsafe_allow_html=True,
        )

        base = alt.Chart(viz["comp_df"]).encode(theta=alt.Theta("Count", stack=True))

        pie = (
            base.mark_arc(innerRadius=50, outerRadius=80)
            .encode(
                color=alt.Color("Element", scale=alt.Scale(scheme="set2")),
                order=alt.Order("Count", sort="descending"),
                tooltip=["Element", "Count", alt.Tooltip("Fraction", format=".1%")],
            )
            .properties(height=180)
        )

        text = base.mark_text(radius=90).encode(
            text=alt.Text("Element"),
            order=alt.Order("Count", sort="descending"),
            color=alt.value("#4a5568"),
        )

        st.altair_chart(pie + text, use_container_width=True)

        elements_str = ", ".join(viz["comp_df"]["Element"].tolist())
        st.markdown(
            f"""
            <div class="finding-box">
                <div class="finding-title">🔍 组分分析</div>
                <div class="finding-text">
                    该结构包含 <span class="highlight">{len(viz['comp_df'])} 种元素</span>：{elements_str}。
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown(
        """
        <div class="chart-toolbar-title">
            <span class="chart-toolbar-index">4</span>
            <span>模拟 XRD 图谱 (Cu-Kα, λ=1.5406 Å)</span>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if not viz["xrd_df"].empty:
        chart_xrd = (
            alt.Chart(viz["xrd_df"])
            .mark_rule(size=2, color="#f59e0b")
            .encode(
                x=alt.X("2Theta:Q", title="2θ (Degrees)", scale=alt.Scale(zero=False)),
                y=alt.Y("Intensity:Q", title="Intensity (%)"),
                tooltip=["2Theta", "Intensity", "HKL"],
            )
            .properties(height=220)
            .configure_axis(gridColor="#f1f5f9", domainColor="#cbd5e0")
            .configure_view(strokeWidth=0)
        )
        st.altair_chart(chart_xrd, use_container_width=True)

        strongest_peak = viz["xrd_df"].loc[viz["xrd_df"]["Intensity"].idxmax()]
        st.markdown(
            f"""
            <div class="finding-box">
                <div class="finding-title">🔍 衍射特征</div>
                <div class="finding-text">
                    最强衍射峰出现在 <span class="highlight">2θ = {strongest_peak['2Theta']:.1f}°</span>，
                    对应的晶面指数为 ({strongest_peak['HKL']})。这是识别该晶相的主要指纹特征。
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    else:
        st.info("无法生成 XRD 数据（可能是非周期性结构或解析错误）。")

    st.markdown(
        f"<div style='text-align:right; font-size:0.7rem; color:#cbd5e0; margin-top:0.5rem;'>Source File: {filename}</div>",
        unsafe_allow_html=True,
    )
