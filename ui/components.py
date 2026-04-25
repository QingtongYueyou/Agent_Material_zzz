from __future__ import annotations

import streamlit as st

from config.settings import CIF_DIR


def render_top_bar() -> None:
    st.markdown(
        """
        <div class="top-bar">
            <div class="top-bar-left">
                <div style="font-size: 1.3rem; font-weight: 700; color: #1a202c;">
                    材料智能分析系统
                </div>
            </div>
            <div style="display: flex; gap: 0.8rem; align-items: center;">
                <span class="badge badge-blue">Function Calling</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _label_for_step(step_name: str) -> str:
    labels = {
        "function_calling": "工具决策",
        "search_materials_by_criteria": "材料检索",
        "get_mp_structure": "结构获取",
        "visualization_generation": "可视化准备",
        "answer_composition": "答案生成",
    }
    return labels.get(step_name, step_name)


def render_agent_logs() -> None:
    trace = st.session_state.get("workflow_trace", [])

    st.markdown(
        """
        <div style="display: flex; align-items: center; gap: 0.6rem; margin-bottom: 0.8rem;">
            <span class="section-label label-c">C</span>
            <span style="font-size: 1rem; font-weight: 700; color: #1a202c;">执行轨迹</span>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if not trace:
        st.markdown(
            """
            <div class="card" style="text-align: center; padding: 2rem 1rem; color: #94a3b8;">
                <div>等待任务启动...</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        return

    st.caption("真实步骤状态 / 耗时 / 错误信息")
    html = '<div class="task-flow-container">'

    icon_map = {
        "success": "✓",
        "failed": "✕",
        "skipped": "○",
        "running": "…",
    }

    for row in trace:
        step_name = str(row.get("step_name", ""))
        status = str(row.get("status", "running"))
        latency_ms = int(row.get("latency_ms", 0) or 0)
        err = row.get("error_message")
        fallback = row.get("fallback_used", False)

        icon = icon_map.get(status, "…")
        status_class = "done" if status == "success" else "running"
        detail = f"状态: {status} | 耗时: {latency_ms} ms"
        if fallback:
            detail += " | fallback: yes"
        if err:
            detail += f" | error: {err}"

        html += f"""
<div class="task-node {status_class}" style="border-left: 3px solid #cbd5e0; margin-left: 10px;">
<div class="task-status {status_class}" style="margin-left: -23px;">{icon}</div>
<div style="flex:1;">
<div style="font-size:0.75rem; font-weight:700; color:#4a5568;">{_label_for_step(step_name)}</div>
<div class="task-label" style="font-size:0.8rem;">{detail}</div>
</div>
</div>
"""

    html += "</div>"
    st.markdown(html, unsafe_allow_html=True)


def render_task_panel() -> None:
    render_agent_logs()

    st.markdown(
        """
        <div style="margin-top: 1rem;">
            <div style="display: flex; align-items: center; gap: 0.6rem; margin-bottom: 0.8rem;">
                <span class="section-label label-c">D</span>
                <span style="font-size: 1rem; font-weight: 700; color: #1a202c;">数据摘要</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    viz_data = st.session_state.get("viz_data")
    if viz_data is not None:
        st.markdown('<div class="card">', unsafe_allow_html=True)
        st.caption(f"源文件: {viz_data['filename']}")
        st.dataframe(viz_data["lattice_df"], use_container_width=True, hide_index=True)
        if viz_data["xrd_df"].empty:
            st.warning("有晶格数据，但未生成 XRD 图谱")
        st.markdown("</div>", unsafe_allow_html=True)
    else:
        st.caption("暂无数据，请在左侧开始对话")


def render_debug_sidebar() -> None:
    st.divider()
    st.header("调试面板")
    st.write(f"当前扫描路径: `{CIF_DIR}`")

    if CIF_DIR.exists():
        files = list(CIF_DIR.iterdir())
        st.write(f"文件数量: {len(files)}")
        if files:
            st.write("最新文件")
            st.code(files[-1].name)
        else:
            st.warning("文件夹为空")
    else:
        st.error("文件夹不存在")

    trace = st.session_state.get("workflow_trace", [])
    st.write(f"工作流步骤数: {len(trace)}")
    trace_id = st.session_state.get("trace_id")
    if trace_id:
        st.code(trace_id)
