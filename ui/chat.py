from __future__ import annotations

import streamlit as st


def render_chat_panel() -> str | None:
    st.markdown(
        """
        <div class="chat-wrapper">
            <div class="chat-header">
                <div class="chat-header-title">
                    <span>💬</span>
                    <span>对话与控制</span>
                </div>
                <div class="chat-status">在线</div>
            </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown('<div class="chat-container">', unsafe_allow_html=True)

    if len(st.session_state.messages) == 0:
        st.markdown(
            """
            <div class="card" style="height: 200px; display: flex; align-items: center; justify-content: center; color: #94a3b8;">
                <div style="text-align: center; padding: 0 1rem;">
                    <div style="font-size: 2rem; margin-bottom: 0.5rem;">👋</div>
                    <div style="font-size: 0.85rem;">你好！我是材料分析助手</div>
                    <div style="font-size: 0.75rem; margin-top: 0.3rem;">请在下方输入您的问题开始对话</div>
                    <div style="font-size: 0.65rem; margin-top: 0.5rem; color: #cbd5e0;">支持根据 MP-ID 或化学式生成结构图表</div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    st.markdown("</div>", unsafe_allow_html=True)

    user_input = st.chat_input("💭 输入材料相关问题，如：LiFePO4 的晶体结构...")

    st.markdown("</div>", unsafe_allow_html=True)

    return user_input
