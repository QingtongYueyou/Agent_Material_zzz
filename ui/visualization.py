from __future__ import annotations

import os
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

import altair as alt
import streamlit as st
import streamlit.components.v1 as components

from config.settings import BASE_DIR, SPLAT_DIR
from core.processor import HAS_PYMATGEN


class _CORSRequestHandler(SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        super().end_headers()


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
    material_name = filename.split("_")[0]

    search_candidates = [
        os.path.join(SPLAT_DIR, f"{cif_basename}.ply"),
        os.path.join(SPLAT_DIR, f"{cif_basename}.splat"),
        os.path.join(SPLAT_DIR, f"{material_name}.ply"),
        os.path.join(SPLAT_DIR, f"{material_name}.splat"),
        f"GLOB:{os.path.join(SPLAT_DIR, f'*{material_name}*.ply')}",
        os.path.join(SPLAT_DIR, "object.ply"),
    ]

    found_splat_path = None

    for candidate in search_candidates:
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

        port = _ensure_static_server(str(BASE_DIR), port=8001)
        model_url = f"http://127.0.0.1:{port}/static/splat_files/{file_name_only}"

        file_ext = os.path.splitext(file_name_only)[1].lower()
        format_enum = "GaussianSplats3D.SceneFormat.Ply"
        if file_ext == ".splat":
            format_enum = "GaussianSplats3D.SceneFormat.Splat"
        elif file_ext == ".ksplat":
            format_enum = "GaussianSplats3D.SceneFormat.KSplat"

        if file_name_only == "object.ply" and material_name not in file_name_only:
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

                            const viewer = new GaussianSplats3D.Viewer({{
                                'rootElement': container,
                                'cameraUp': [0, 1, 0],
                                'initialCameraPosition': [2, 2, 5],
                                'initialCameraLookAt': [0, 0, 0],
                                'selfDrivenMode': true,
                                'useBuiltInControls': true,
                                'sharedMemoryForWorkers': false,
                                'gpuAcceleratedSort': false
                            }});

                            viewer.addSplatScene("{model_url}", {{
                                'format': {format_enum},
                                'scale': [1, 1, 1],
                                'splatAlphaRemovalThreshold': 5,
                                'showLoadingUI': false
                            }})
                            .then(() => {{
                                viewer.start();
                                loadingLabel.style.display = 'none';

                                let frameCount = 0;
                                let lastTime = performance.now();

                                function updateFPS() {{
                                    const now = performance.now();
                                    frameCount++;

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
                            }})
                            .catch((err) => {{
                                console.error("Splat load error:", err);
                                loadingLabel.style.background = "rgba(220, 38, 38, 0.9)";
                                progressText.innerText = "Error: Check Console";
                            }});
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
