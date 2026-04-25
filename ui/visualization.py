from __future__ import annotations

import json
import os
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

import altair as alt
import streamlit as st
import streamlit.components.v1 as components

from config.settings import BASE_DIR, SPLAT_DIR
from core.perf_metrics import (
    append_interaction_metric,
    append_render_metric,
    get_ply_vertex_count,
)
from core.processor import HAS_PYMATGEN


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

    st.markdown(
        """
        <div class="card" style="margin-bottom: 1rem;">
            <div class="card-header">
                <div class="card-number">0</div>
                <div class="card-title">3D Gaussian Splatting 视图 (WebGL)</div>
                <div class="card-icon">✨</div>
            </div>
        """,
        unsafe_allow_html=True,
    )

    cif_basename = os.path.splitext(filename)[0]
    parts = cif_basename.split("_", 1)
    material_name = parts[0]
    formula_name = parts[1] if len(parts) > 1 else ""

    search_candidates = [
        os.path.join(SPLAT_DIR, f"{cif_basename}.ply"),
        os.path.join(SPLAT_DIR, f"{cif_basename}.splat"),
        os.path.join(SPLAT_DIR, f"{material_name}.ply"),
        os.path.join(SPLAT_DIR, f"{material_name}.splat"),
        os.path.join(SPLAT_DIR, f"{formula_name}.ply") if formula_name else "",
        os.path.join(SPLAT_DIR, f"{formula_name}.splat") if formula_name else "",
        f"GLOB:{os.path.join(SPLAT_DIR, f'*{formula_name}*.ply')}" if formula_name else "",
        f"GLOB:{os.path.join(SPLAT_DIR, f'*{material_name}*.ply')}",
        os.path.join(SPLAT_DIR, "object.ply"),
    ]

    found_splat_path = None

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
        file_name_only = os.path.basename(found_splat_path)
        file_ext = os.path.splitext(file_name_only)[1].lower()
        vertex_count = get_ply_vertex_count(found_splat_path)
        vertex_count_label = "未知" if vertex_count is None else str(vertex_count)
        file_size_bytes = os.path.getsize(found_splat_path)
        file_mtime = int(os.path.getmtime(found_splat_path))

        port = _ensure_static_server(str(BASE_DIR), port=8001)
        model_url = f"http://127.0.0.1:{port}/static/splat_files/{file_name_only}?v={file_mtime}"
        metrics_url = f"http://127.0.0.1:{port}/__perf/render-metrics"
        interaction_metrics_url = f"http://127.0.0.1:{port}/__perf/interaction-metrics"

        format_enum = "GaussianSplats3D.SceneFormat.Ply"
        if file_ext == ".splat":
            format_enum = "GaussianSplats3D.SceneFormat.Splat"
        elif file_ext == ".ksplat":
            format_enum = "GaussianSplats3D.SceneFormat.KSplat"

        if file_name_only == "object.ply":
            st.caption(f"ℹ️ 未找到专属模型，展示测试文件: `{file_name_only}`")
        else:
            st.caption(f"✅ 已加载模型: `{file_name_only}`")

        gs_html = f"""
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
        components.html(gs_html, height=350)
    else:
        st.warning("⚠️ 在 `static/splat_files` 中未找到匹配的模型文件。")
        st.markdown(f"<small>搜索路径: {SPLAT_DIR}</small>", unsafe_allow_html=True)

    st.markdown("</div>", unsafe_allow_html=True)

    viz_col1, viz_col2 = st.columns(2, gap="medium")

    with viz_col1:
        st.markdown(
            """
            <div class="card">
                <div class="card-header">
                    <div class="card-number">1</div>
                    <div class="card-title">晶胞参数 (Lattice)</div>
                    <div class="card-icon">📏</div>
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
            </div>
            """,
            unsafe_allow_html=True,
        )

    with viz_col2:
        st.markdown(
            """
            <div class="card">
                <div class="card-header">
                    <div class="card-number">2</div>
                    <div class="card-title">化学组分 (Composition)</div>
                    <div class="card-icon">🧪</div>
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
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown(
        """
        <div class="card">
            <div class="card-header">
                <div class="card-number">3</div>
                <div class="card-title">模拟 XRD 图谱 (Cu-Kα, λ=1.5406 Å)</div>
                <div class="card-icon">📉</div>
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
        f"<div style='text-align:right; font-size:0.7rem; color:#cbd5e0; margin-top:0.5rem;'>Source File: {filename}</div></div>",
        unsafe_allow_html=True,
    )
