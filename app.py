from __future__ import annotations

import glob
import os

import streamlit as st

from config.settings import CIF_DIR
from core.agent import materials_agent
from core.processor import get_latest_cif_info
from ui.chat import render_chat_panel
from ui.components import (
    get_agent_response_stream,
    render_debug_sidebar,
    render_task_panel,
    render_top_bar,
)
from ui.styles import apply_styles
from ui.visualization import render_visualization_panel


def _init_session_state() -> None:
    defaults = {
        "messages": [],
        "viz_data": None,
        "last_question": "",
        "tasks": [],
        "table_df": None,
        "selected_task_id": None,
        "selected_material": None,
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

render_top_bar()

col_left, col_middle, col_right = st.columns([4.2, 6.8, 4.0], gap="medium")

with col_left:
    user_input = render_chat_panel()

if user_input:
    st.session_state.last_question = user_input
    st.session_state.messages.append({"role": "user", "content": user_input})
    st.session_state.processing = True
    st.rerun()

with col_middle:
    render_visualization_panel()

with col_right:
    log_container = st.empty()
    render_task_panel(log_container)

if st.session_state.get("processing", False):
    with col_left:
        try:
            user_question = st.session_state.last_question

            files = glob.glob(os.path.join(str(CIF_DIR), "*"))
            for f in files:
                try:
                    os.remove(f)
                except Exception:
                    pass

            st.session_state.agent_logs = []

            with st.chat_message("assistant"):
                reply_text = st.write_stream(
                    get_agent_response_stream(materials_agent, user_question, log_container)
                )

            st.session_state.messages.append({"role": "assistant", "content": reply_text})

            cif_name, lat_df, el_df, xrd_df = get_latest_cif_info()

            if cif_name:
                st.session_state.viz_data = {
                    "filename": cif_name,
                    "lattice_df": lat_df,
                    "comp_df": el_df,
                    "xrd_df": xrd_df,
                }

        except Exception as e:
            st.error(f"运行出错: {e}")
        finally:
            st.session_state.processing = False
            st.rerun()

with st.sidebar:
    render_debug_sidebar()
