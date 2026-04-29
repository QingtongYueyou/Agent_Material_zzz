from __future__ import annotations

import streamlit as st

from core.spark_asset_ingest import ensure_auto_ingest_started
from core.workflow import WorkflowOrchestrator
from ui.chat import render_chat_panel
from ui.components import render_debug_sidebar, render_task_panel, render_top_bar
from ui.styles import apply_styles
from ui.visualization import render_visualization_panel


def _init_session_state() -> None:
    defaults = {
        "messages": [],
        "viz_data": None,
        "last_question": "",
        "workflow_trace": [],
        "trace_id": "",
        "selected_task_id": None,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


st.set_page_config(
    page_title="材料智能分析系统",
    layout="wide",
    initial_sidebar_state="collapsed",
)

apply_styles()
_init_session_state()
ensure_auto_ingest_started()

render_top_bar()

col_left, col_middle, col_right = st.columns([4.2, 6.8, 4.0], gap="medium")

with col_left:
    user_input = render_chat_panel()

if user_input:
    st.session_state.last_question = user_input
    st.session_state.messages.append({"role": "user", "content": user_input})
    st.session_state.workflow_trace = []
    st.session_state.processing = True
    st.rerun()

with col_middle:
    render_visualization_panel()

with col_right:
    render_task_panel()

if st.session_state.get("processing", False):
    with col_left:
        try:
            user_question = st.session_state.last_question
            orchestrator = WorkflowOrchestrator()

            final_payload = None
            for event in orchestrator.run_stream(user_question):
                if event.get("type") == "step_end":
                    st.session_state.workflow_trace.append(
                        {
                            "step_name": event.get("step"),
                            "status": event.get("status"),
                            "latency_ms": event.get("latency_ms", 0),
                            "error_message": event.get("error"),
                            "fallback_used": event.get("fallback_used", False),
                        }
                    )
                elif event.get("type") == "final":
                    final_payload = event

            if final_payload is None:
                final_payload = {
                    "answer": "工作流未返回最终结果。",
                    "step_results": st.session_state.workflow_trace,
                    "viz": None,
                    "trace_id": "",
                }

            st.session_state.trace_id = final_payload.get("trace_id", "")
            st.session_state.workflow_trace = final_payload.get("step_results", st.session_state.workflow_trace)

            with st.chat_message("assistant"):
                st.markdown(final_payload.get("answer", ""))

            st.session_state.messages.append(
                {"role": "assistant", "content": final_payload.get("answer", "")}
            )

            viz_data = final_payload.get("viz")
            if isinstance(viz_data, dict) and viz_data.get("filename"):
                st.session_state.viz_data = viz_data

        except Exception as e:
            st.error(f"运行出错: {e}")
        finally:
            st.session_state.processing = False
            st.rerun()

with st.sidebar:
    render_debug_sidebar()
