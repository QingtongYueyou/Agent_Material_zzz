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
                <span class="badge badge-blue">网格视图</span>
                <span class="badge badge-gray">导出代码</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def generate_real_tasks():
    tasks = []

    is_processing = st.session_state.get("processing", False)

    last_q = st.session_state.get("last_question", "")
    has_question = bool(last_q)

    tasks.append(
        {
            "id": "T1",
            "label": f"意图识别: {last_q[:15]}..." if has_question else "等待用户提问...",
            "status": "done" if has_question else "pending",
            "progress": "100%" if has_question else "0%",
        }
    )

    viz_data = st.session_state.get("viz_data")
    has_data = viz_data is not None

    if has_data:
        t2_status = "done"
        t2_progress = "100%"
    elif is_processing:
        t2_status = "running"
        t2_progress = "45%"
    else:
        t2_status = "pending"
        t2_progress = "0%"

    tasks.append(
        {
            "id": "T2",
            "label": "Materials Project 接口调用与落地",
            "status": t2_status,
            "progress": t2_progress,
        }
    )

    messages = st.session_state.get("messages", [])
    has_reply = False
    if messages and messages[-1]["role"] == "assistant" and not is_processing:
        has_reply = True

    if has_reply:
        t3_status = "done"
        t3_progress = "100%"
    elif is_processing:
        t3_status = "running" if has_data else "pending"
        t3_progress = "20%"
    else:
        t3_status = "pending"
        t3_progress = "0%"

    tasks.append(
        {
            "id": "T3",
            "label": "晶体结构分析与 Agent 推理",
            "status": t3_status,
            "progress": t3_progress,
        }
    )

    t4_status = "pending"
    t4_progress = "0%"

    if has_data and not is_processing:
        if not viz_data["xrd_df"].empty:
            t4_status = "done"
            t4_progress = "100%"
        else:
            t4_status = "running"
            t4_progress = "50%"

    tasks.append(
        {
            "id": "T4",
            "label": "可视化图表渲染 (Lattice/XRD)",
            "status": t4_status,
            "progress": t4_progress,
        }
    )

    return tasks


def render_task_flow_simple(tasks) -> None:
    for t in tasks:
        icon_map = {"done": "✓", "running": "⟳", "pending": "○"}
        status_icon = icon_map.get(t["status"], "○")

        status_class = t["status"]
        current_selected_id = st.session_state.get("selected_task_id")
        active_class = "active" if t["id"] == current_selected_id else ""

        st.markdown(
            f"""
            <div class="task-node {status_class} {active_class}">
                <div class="task-status {status_class}">{status_icon}</div>
                <div class="task-label">{t['label']}</div>
                <div class="task-progress">{t['progress']}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )


def get_agent_response_stream(agent, question, log_placeholder):
    st.session_state.agent_logs = [
        {
            "step": "Planning",
            "detail": "识别用户意图 (Intent Recognition)...",
            "status": "done",
        },
        {
            "step": "Retrieval",
            "detail": "检索 Materials Project 数据库 (API Call)...",
            "status": "done",
        },
        {
            "step": "Reasoning",
            "detail": "分析晶体结构与性质关联 (CoT)...",
            "status": "running",
        },
    ]

    render_agent_logs(log_placeholder)

    stream = agent.run(question, stream=True)

    for chunk in stream:
        content = None
        if hasattr(chunk, "content"):
            content = chunk.content
        elif isinstance(chunk, str):
            content = chunk
        if content is None and hasattr(chunk, "choices") and chunk.choices:
            if hasattr(chunk.choices[0], "delta") and hasattr(
                chunk.choices[0].delta, "content"
            ):
                content = chunk.choices[0].delta.content

        if content:
            yield content

    st.session_state.agent_logs[2]["status"] = "done"

    st.session_state.agent_logs.append(
        {
            "step": "Final Answer",
            "detail": "生成最终回复与可视化图表",
            "status": "done",
        }
    )

    render_agent_logs(log_placeholder)


def render_agent_logs(placeholder) -> None:
    if "agent_logs" not in st.session_state:
        return

    with placeholder.container():
        st.markdown(
            """
            <div style="display: flex; align-items: center; gap: 0.6rem; margin-bottom: 0.8rem;">
                <span class="section-label label-c">C</span>
                <span style="font-size: 1rem; font-weight: 700; color: #1a202c;">智能编排</span>
            </div>
            """,
            unsafe_allow_html=True,
        )

        st.caption("🤖 Agent 思维链 (Chain of Thought)")

        html_content = '<div class="task-flow-container">'

        for i, log in enumerate(st.session_state.agent_logs):
            is_last = i == len(st.session_state.agent_logs) - 1
            status_icon = "✓" if log["status"] == "done" else "⟳"
            status_class = "done" if log["status"] == "done" else "running"

            if is_last and log["status"] != "done":
                status_class = "running"
            else:
                status_class = "done"

            html_content += f"""
<div class="task-node {status_class}" style="border-left: 3px solid #cbd5e0; margin-left: 10px;">
<div class="task-status {status_class}" style="margin-left: -23px;">{status_icon}</div>
<div style="flex:1;">
<div style="font-size:0.75rem; font-weight:700; color:#4a5568;">{log['step']}</div>
<div class="task-label" style="font-size:0.8rem;">{log['detail']}</div>
</div>
</div>"""

        html_content += "</div>"

        st.markdown(html_content, unsafe_allow_html=True)


def render_task_panel(log_container) -> None:
    if not st.session_state.messages and not st.session_state.get("processing", False):
        st.markdown(
            """
            <div style="display: flex; align-items: center; gap: 0.6rem; margin-bottom: 0.8rem;">
                <span class="section-label label-c">C</span>
                <span style="font-size: 1rem; font-weight: 700; color: #1a202c;">智能编排</span>
            </div>
            <div class="card" style="height: 140px;"></div>
            """,
            unsafe_allow_html=True,
        )
        st.markdown(
            """
            <div style="margin-top: 1rem;">
                <div style="display: flex; align-items: center; gap: 0.6rem; margin-bottom: 0.8rem;">
                    <span class="section-label label-c">D</span>
                    <span style="font-size: 1rem; font-weight: 700; color: #1a202c;">数据追溯</span>
                </div>
                <div style="font-size: 0.8rem; color: #64748b; margin-bottom: 0.8rem;">
                    📋 数据表格 · <span class="badge badge-yellow">表格透镜</span>
                </div>
            </div>
            <div class="card" style="height: 140px;"></div>
            """,
            unsafe_allow_html=True,
        )
        return

    if not st.session_state.get("processing", False) and "agent_logs" in st.session_state:
        render_agent_logs(log_container)

    if "agent_logs" not in st.session_state:
        with log_container.container():
            st.markdown(
                """
                <div style="display: flex; align-items: center; gap: 0.6rem; margin-bottom: 0.8rem;">
                    <span class="section-label label-c">C</span>
                    <span style="font-size: 1rem; font-weight: 700; color: #1a202c;">智能编排</span>
                </div>
                <div class="card" style="text-align: center; padding: 2rem 1rem; color: #94a3b8;">
                    <div>🤖</div>
                    <div style="font-size: 0.85rem; margin-top: 0.5rem;">等待任务启动...</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

    st.markdown(
        """
        <div style="margin-top: 1rem;">
            <div style="display: flex; align-items: center; gap: 0.6rem; margin-bottom: 0.8rem;">
                <span class="section-label label-c">D</span>
                <span style="font-size: 1rem; font-weight: 700; color: #1a202c;">数据追溯</span>
            </div>
            <div style="font-size: 0.8rem; color: #64748b; margin-bottom: 0.8rem;">
                📋 数据表格 · <span class="badge badge-yellow">表格透镜</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if st.session_state.viz_data is not None:
        st.markdown('<div class="card">', unsafe_allow_html=True)
        st.caption(f"源文件: {st.session_state.viz_data['filename']}")
        df_table = st.session_state.viz_data["lattice_df"]
        st.dataframe(df_table, use_container_width=True, hide_index=True)
        if st.session_state.viz_data["xrd_df"].empty:
            st.warning("⚠️ 提示: 检测到晶格数据，但未生成 XRD 图谱 (可能是非周期性结构)")
        st.markdown("</div>", unsafe_allow_html=True)
    else:
        st.caption("📊 暂无数据，请在左侧开始对话")


def render_debug_sidebar() -> None:
    st.divider()
    st.header("🔧 调试面板")
    st.write(f"**当前扫描路径:** `{CIF_DIR}`")

    if CIF_DIR.exists():
        files = list(CIF_DIR.iterdir())
        st.write(f"**文件数量:** {len(files)}")
        if len(files) > 0:
            st.write("**最新文件:**")
            st.code(files[-1].name)
        else:
            st.error("文件夹为空！Agent 没有生成文件。")
            st.info("可能原因：API Key 无效，或者 Agent 没有调用下载工具。")
    else:
        st.error("文件夹不存在！")

    if "viz_data" in st.session_state and st.session_state.viz_data:
        st.success("✅ viz_data 已加载")
    else:
        st.warning("⏳ viz_data 为空")
