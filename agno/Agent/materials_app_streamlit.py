# materials_app_streamlit_lightva_cn.py

import streamlit as st
import pandas as pd
import altair as alt

try:
    import graphviz

    HAS_GRAPHVIZ = True
except ImportError:
    HAS_GRAPHVIZ = False

from material_chatbot import materials_agent

# ------------------ 页面基础设置 ------------------

st.set_page_config(
    page_title="材料智能分析系统",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# ------------------ LightVA 风格样式（中文优化 + iOS 气泡） ------------------

st.markdown(
    """
    <style>
    /* 字体 */
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');

    /* 全局背景 - 浅灰色 */
    html, body, [class*="stApp"] {
        background: #f5f7fb !important;
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'PingFang SC', 'Microsoft YaHei', sans-serif;
        color: #2d3748;
    }

    /* 主容器 */
    .block-container {
        padding: 1.5rem 2rem;
        max-width: 100%;
    }

    /* === 顶部标题栏 === */
    .top-bar {
        background: white;
        border-radius: 12px;
        padding: 1rem 1.5rem;
        margin-bottom: 1rem;
        box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
        border: 1px solid #e2e8f0;
        display: flex;
        align-items: center;
        justify-content: space-between;
    }

    .top-bar-left {
        display: flex;
        align-items: center;
        gap: 1rem;
    }

    .section-label {
        display: inline-block;
        background: #cbd5e0;
        color: #2d3748;
        padding: 0.25rem 0.75rem;
        border-radius: 6px;
        font-size: 0.7rem;
        font-weight: 600;
        letter-spacing: 0.05em;
    }

    .section-label.label-a {
        background: #e0e7ff;
        color: #4c51bf;
    }

    .section-label.label-b {
        background: #fef3c7;
        color: #d97706;
    }

    .section-label.label-c {
        background: #dbeafe;
        color: #1e40af;
    }

    .section-title {
        font-size: 0.95rem;
        font-weight: 600;
        color: #1a202c;
        margin: 0;
    }

    /* === 三栏布局容器 === */
    .column-container {
        display: flex;
        gap: 1rem;
        height: calc(100vh - 180px);
    }

    /* 左栏（聊天控制）*/
    .left-column {
        flex: 0 0 380px;
        display: flex;
        flex-direction: column;
        gap: 1rem;
    }

    /* 中栏（可视化）*/
    .middle-column {
        flex: 1;
        display: flex;
        flex-direction: column;
        gap: 1rem;
        overflow-y: auto;
    }

    /* 右栏（任务追溯）*/
    .right-column {
        flex: 0 0 420px;
        display: flex;
        flex-direction: column;
        gap: 1rem;
        overflow-y: auto;
    }

    /* === 卡片样式 === */
    .card {
        background: white;
        border-radius: 10px;
        padding: 1rem;
        box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
        border: 1px solid #e2e8f0;
    }

    .card-header {
        display: flex;
        align-items: center;
        gap: 0.5rem;
        margin-bottom: 0.8rem;
        padding-bottom: 0.6rem;
        border-bottom: 1px solid #e2e8f0;
    }

    .card-number {
        width: 28px;
        height: 28px;
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white;
        border-radius: 50%;
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 0.85rem;
        font-weight: 700;
    }

    .card-title {
        font-size: 0.9rem;
        font-weight: 600;
        color: #2d3748;
        flex: 1;
        line-height: 1.3;
    }

    .card-icon {
        font-size: 1.1rem;
        cursor: pointer;
        opacity: 0.6;
        transition: opacity 0.2s;
    }

    .card-icon:hover {
        opacity: 1;
    }

    /* === Finding 区域 === */
    .finding-box {
        background: #fffbeb;
        border-left: 3px solid #f59e0b;
        border-radius: 6px;
        padding: 0.8rem 1rem;
        margin-top: 0.8rem;
    }

    .finding-title {
        display: flex;
        align-items: center;
        gap: 0.4rem;
        font-size: 0.8rem;
        font-weight: 600;
        color: #92400e;
        margin-bottom: 0.4rem;
    }

    .finding-text {
        font-size: 0.8rem;
        color: #78350f;
        line-height: 1.5;
    }

    /* 高亮词 */
    .highlight {
        background: #bfdbfe;
        color: #1e40af;
        padding: 2px 6px;
        border-radius: 4px;
        font-weight: 500;
    }

    /* === iOS 风格聊天区域 === */
    .chat-wrapper {
        flex: 1;
        display: flex;
        flex-direction: column;
        background: white;
        border-radius: 10px;
        overflow: hidden;
        box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
        border: 1px solid #e2e8f0;
    }

    .chat-header {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        padding: 0.8rem 1rem;
        color: white;
        display: flex;
        align-items: center;
        justify-content: space-between;
    }

    .chat-header-title {
        font-size: 0.9rem;
        font-weight: 600;
        display: flex;
        align-items: center;
        gap: 0.5rem;
    }

    .chat-status {
        font-size: 0.7rem;
        background: rgba(255, 255, 255, 0.2);
        padding: 0.2rem 0.6rem;
        border-radius: 12px;
    }

    .chat-container {
        flex: 1;
        overflow-y: auto;
        padding: 1rem;
        background: #f8fafc;
    }

    .chat-container::-webkit-scrollbar {
        width: 5px;
    }

    .chat-container::-webkit-scrollbar-track {
        background: transparent;
    }

    .chat-container::-webkit-scrollbar-thumb {
        background: #cbd5e0;
        border-radius: 10px;
    }

    /* iOS 聊天气泡样式 */
    div[data-testid="stChatMessage"] {
        padding: 0;
        margin-bottom: 0.8rem;
        background: transparent !important;
    }

    /* 用户消息气泡 - iOS 蓝色 */
    div[data-testid="stChatMessage"][data-testid*="user"] {
        display: flex;
        justify-content: flex-end;
    }

    div[data-testid="stChatMessage"][data-testid*="user"] > div {
        background: linear-gradient(135deg, #007AFF 0%, #5856D6 100%) !important;
        border-radius: 18px !important;
        border-bottom-right-radius: 4px !important;
        padding: 0.75rem 1rem !important;
        color: white !important;
        box-shadow: 0 2px 12px rgba(0, 122, 255, 0.3) !important;
        max-width: 75% !important;
        margin-left: auto !important;
        font-size: 0.85rem !important;
        line-height: 1.5 !important;
        word-wrap: break-word;
    }

    /* AI 助手消息气泡 - iOS 灰色 */
    div[data-testid="stChatMessage"][data-testid*="assistant"] {
        display: flex;
        justify-content: flex-start;
    }

    div[data-testid="stChatMessage"][data-testid*="assistant"] > div {
        background: white !important;
        border-radius: 18px !important;
        border-bottom-left-radius: 4px !important;
        padding: 0.75rem 1rem !important;
        color: #1a202c !important;
        box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08) !important;
        border: 1px solid #e2e8f0 !important;
        max-width: 75% !important;
        font-size: 0.85rem !important;
        line-height: 1.5 !important;
        word-wrap: break-word;
    }

    /* 消息时间戳（如果需要） */
    .message-time {
        font-size: 0.65rem;
        color: #94a3b8;
        margin-top: 0.3rem;
        text-align: right;
    }

    /* 聊天输入框 - iOS 风格 */
    .chat-input-wrapper {
        padding: 0.8rem 1rem;
        background: white;
        border-top: 1px solid #e2e8f0;
    }

    .stChatInput {
        border-radius: 20px !important;
        border: 1px solid #cbd5e0 !important;
        background: #f7fafc !important;
        box-shadow: 0 2px 4px rgba(0, 0, 0, 0.04) !important;
    }

    .stChatInput input {
        font-size: 0.85rem !important;
        padding: 0.7rem 1.2rem !important;
        border-radius: 20px !important;
    }

    .stChatInput input:focus {
        border-color: #667eea !important;
        box-shadow: 0 0 0 3px rgba(102, 126, 234, 0.1) !important;
    }

    /* 输入框占位符 */
    .stChatInput input::placeholder {
        color: #94a3b8;
    }

    /* === 任务流程图 === */
    .task-flow-container {
        background: #f8fafc;
        border-radius: 8px;
        padding: 1rem;
        margin: 0.5rem 0;
    }

    .task-node {
        background: white;
        border: 2px solid #e2e8f0;
        border-radius: 8px;
        padding: 0.6rem 0.8rem;
        margin-bottom: 0.5rem;
        display: flex;
        align-items: center;
        gap: 0.6rem;
        cursor: pointer;
        transition: all 0.2s;
    }

    .task-node:hover {
        border-color: #667eea;
        box-shadow: 0 2px 8px rgba(102, 126, 234, 0.2);
        transform: translateX(2px);
    }

    .task-node.active {
        background: #eef2ff;
        border-color: #667eea;
        box-shadow: 0 0 0 3px rgba(102, 126, 234, 0.1);
    }

    .task-node.completed {
        background: #f0fdf4;
        border-color: #10b981;
    }

    .task-status {
        width: 22px;
        height: 22px;
        border-radius: 50%;
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 0.7rem;
        flex-shrink: 0;
        font-weight: 600;
    }

    .task-status.done {
        background: #10b981;
        color: white;
    }

    .task-status.running {
        background: #3b82f6;
        color: white;
        animation: pulse 2s ease-in-out infinite;
    }

    @keyframes pulse {
        0%, 100% { opacity: 1; }
        50% { opacity: 0.6; }
    }

    .task-status.pending {
        background: #e2e8f0;
        color: #64748b;
    }

    .task-label {
        font-size: 0.8rem;
        color: #475569;
        line-height: 1.3;
        flex: 1;
    }

    .task-progress {
        font-size: 0.7rem;
        color: #94a3b8;
        font-weight: 600;
    }

    /* === 数据表格 === */
    .data-table-container {
        margin-top: 0.8rem;
    }

    .dataframe {
        border-radius: 8px !important;
        overflow: hidden !important;
        border: 1px solid #e2e8f0 !important;
        font-size: 0.8rem !important;
    }

    .dataframe thead {
        background: #f8fafc !important;
    }

    .dataframe thead th {
        font-weight: 600 !important;
        color: #475569 !important;
        border-bottom: 2px solid #e2e8f0 !important;
        padding: 0.6rem 0.8rem !important;
        font-size: 0.75rem !important;
    }

    .dataframe tbody td {
        padding: 0.6rem 0.8rem !important;
        border-bottom: 1px solid #f1f5f9 !important;
    }

    .dataframe tbody tr:hover {
        background: #f8fafc !important;
    }

    /* === 按钮 === */
    .stButton > button {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%) !important;
        color: white !important;
        border: none !important;
        border-radius: 8px !important;
        padding: 0.5rem 1.2rem !important;
        font-weight: 600 !important;
        font-size: 0.85rem !important;
        transition: all 0.2s !important;
    }

    .stButton > button:hover {
        transform: translateY(-1px);
        box-shadow: 0 4px 12px rgba(102, 126, 234, 0.3) !important;
    }

    /* === 选择器 === */
    .stSelectbox, .stRadio {
        font-size: 0.85rem;
    }

    .stSelectbox select {
        border-radius: 8px !important;
        border: 1px solid #cbd5e0 !important;
        padding: 0.5rem 0.8rem !important;
    }

    .stSelectbox select:focus {
        border-color: #667eea !important;
        box-shadow: 0 0 0 3px rgba(102, 126, 234, 0.1) !important;
    }

    .stRadio > div {
        gap: 0.4rem;
    }

    .stRadio label {
        background: #f8fafc !important;
        border: 1px solid #e2e8f0 !important;
        border-radius: 8px !important;
        padding: 0.5rem 0.8rem !important;
        transition: all 0.2s !important;
    }

    .stRadio label:hover {
        background: #eef2ff !important;
        border-color: #667eea !important;
    }

    /* === Info/Caption === */
    .stAlert {
        background: #eff6ff !important;
        border: 1px solid #bfdbfe !important;
        border-radius: 8px !important;
        font-size: 0.85rem !important;
    }

    .stCaption {
        color: #64748b !important;
        font-size: 0.75rem !important;
        line-height: 1.4 !important;
    }

    /* === 图表 === */
    .vega-embed {
        border-radius: 8px;
    }

    /* === 徽章 === */
    .badge {
        display: inline-block;
        padding: 0.2rem 0.6rem;
        border-radius: 4px;
        font-size: 0.7rem;
        font-weight: 600;
        letter-spacing: 0.02em;
    }

    .badge-blue {
        background: #dbeafe;
        color: #1e40af;
    }

    .badge-green {
        background: #d1fae5;
        color: #065f46;
    }

    .badge-yellow {
        background: #fef3c7;
        color: #92400e;
    }

    .badge-gray {
        background: #f1f5f9;
        color: #475569;
    }

    /* === Task Decomposition === */
    .decomposition-item {
        background: #f8fafc;
        border-left: 3px solid #cbd5e0;
        border-radius: 6px;
        padding: 0.7rem 0.9rem;
        margin-bottom: 0.5rem;
        transition: all 0.2s;
    }

    .decomposition-item:hover {
        background: #eef2ff;
        border-left-color: #667eea;
    }

    .decomposition-item.active {
        background: #eef2ff;
        border-left-color: #667eea;
    }

    .decomposition-title {
        font-size: 0.8rem;
        font-weight: 600;
        color: #1e293b;
        margin-bottom: 0.3rem;
    }

    .decomposition-text {
        font-size: 0.75rem;
        color: #64748b;
        line-height: 1.4;
    }

    /* 隐藏 Streamlit 默认元素 */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}

    /* 响应式 */
    @media (max-width: 1400px) {
        .left-column {
            flex: 0 0 320px;
        }
        .right-column {
            flex: 0 0 360px;
        }
    }

    </style>
    """,
    unsafe_allow_html=True,
)

# ------------------ 状态初始化 ------------------

if "messages" not in st.session_state:
    st.session_state.messages = []

if "chart_df" not in st.session_state:
    st.session_state.chart_df = None

if "chart_caption" not in st.session_state:
    st.session_state.chart_caption = ""

if "last_question" not in st.session_state:
    st.session_state.last_question = ""

if "tasks" not in st.session_state:
    st.session_state.tasks = []

if "table_df" not in st.session_state:
    st.session_state.table_df = None

if "selected_task_id" not in st.session_state:
    st.session_state.selected_task_id = None

if "selected_material" not in st.session_state:
    st.session_state.selected_material = None


# ------------------ 辅助函数 ------------------

def build_example_tasks(question: str):
    short_q = question[:25] + ("…" if len(question) > 25 else "")
    return [
        {"id": "T1", "label": f"理解问题：{short_q}", "status": "done", "progress": "100%"},
        {"id": "T2", "label": "从 Materials Project 获取结构数据", "status": "done", "progress": "100%"},
        {"id": "T3", "label": "分析晶体结构与配位环境", "status": "running", "progress": "60%"},
        {"id": "T4", "label": "生成可视化与结构总结", "status": "pending", "progress": "0%"},
    ]


def render_task_flow_simple(tasks):
    """简化的任务流展示"""
    for i, t in enumerate(tasks):
        status_icon = {"done": "✓", "running": "⟳", "pending": "○"}.get(t["status"], "○")
        status_class = t["status"]
        active_class = "active" if t["id"] == st.session_state.selected_task_id else ""

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


# ------------------ 顶部栏 ------------------
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

# ------------------ 三栏布局 ------------------

col_left, col_middle, col_right = st.columns([3.5, 7, 4.5], gap="medium")

# ==================== A. 左栏：对话与控制 ====================
with col_left:
    # iOS 风格聊天容器
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

    # 聊天消息区域
    st.markdown('<div class="chat-container">', unsafe_allow_html=True)

    if len(st.session_state.messages) == 0:
        st.markdown(
            """
            <div style="text-align: center; padding: 2rem 1rem; color: #94a3b8;">
                <div style="font-size: 2rem; margin-bottom: 0.5rem;">👋</div>
                <div style="font-size: 0.85rem;">你好！我是材料分析助手</div>
                <div style="font-size: 0.75rem; margin-top: 0.3rem;">请在下方输入您的问题开始对话</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    st.markdown("</div>", unsafe_allow_html=True)

    # 聊天输入框
    st.markdown('<div class="chat-input-wrapper">', unsafe_allow_html=True)
    user_input = st.chat_input("💭 输入材料相关问题，如：LiFePO4 的晶体结构...")
    st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("</div>", unsafe_allow_html=True)  # 关闭 chat-wrapper

    if user_input:
        st.session_state.last_question = user_input

        st.session_state.messages.append({"role": "user", "content": user_input})

        with st.spinner("🔍 AI 正在分析中..."):
            result = materials_agent.run(user_input)
            reply_text = getattr(result, "content", str(result))

        st.session_state.messages.append({"role": "assistant", "content": reply_text})

        # 更新数据
        example_df = pd.DataFrame(
            {
                "bandgap_range": ["0–1", "1–2", "2–3", "3–4", "4–5"],
                "count": [2, 5, 8, 3, 1],
            }
        )
        st.session_state.chart_df = example_df
        st.session_state.chart_caption = "候选材料在不同带隙区间的分布"

        st.session_state.tasks = build_example_tasks(user_input)
        st.session_state.selected_task_id = "T3"

        table_df = pd.DataFrame(
            {
                "材料ID": ["mp-1661648", "mp-demo-01", "mp-demo-02", "mp-demo-03"],
                "化学式": ["LiFePO4", "LiMnPO4", "LiCoPO4", "LiNiPO4"],
                "类型": ["目标材料", "候选 A", "候选 B", "候选 C"],
                "评分": [0.86, 0.78, 0.81, 0.75],
            }
        )
        st.session_state.table_df = table_df
        st.session_state.selected_material = table_df["材料ID"].iloc[0]

        st.rerun()

# ==================== B. 中栏：可视化探索 ====================
with col_middle:
    st.markdown(
        """
        <div style="display: flex; align-items: center; gap: 0.6rem; margin-bottom: 0.8rem;">
            <span class="section-label label-b">B</span>
            <span style="font-size: 1rem; font-weight: 700; color: #1a202c;">可视化探索</span>
        </div>
        <div style="font-size: 0.8rem; color: #64748b; margin-bottom: 1rem;">
            📊 可视化视图 · <span class="badge badge-blue">多视图</span>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if st.session_state.chart_df is None:
        st.info("💡 请在左侧开始对话，这里将展示分析可视化结果")
    else:
        # 可视化卡片网格（2x2）
        viz_col1, viz_col2 = st.columns(2, gap="medium")

        # 卡片 2: 带隙分布
        with viz_col1:
            st.markdown(
                """
                <div class="card">
                    <div class="card-header">
                        <div class="card-number">2</div>
                        <div class="card-title">分析候选材料的带隙分布</div>
                        <div class="card-icon">📌</div>
                    </div>
                """,
                unsafe_allow_html=True,
            )

            df_chart = st.session_state.chart_df

            chart = (
                alt.Chart(df_chart)
                .mark_bar(color="#667eea", cornerRadiusTopLeft=6, cornerRadiusTopRight=6)
                .encode(
                    x=alt.X("bandgap_range:N", title="带隙区间 (eV)", axis=alt.Axis(labelAngle=0, labelFontSize=10)),
                    y=alt.Y("count:Q", title="材料数量", axis=alt.Axis(labelFontSize=10)),
                    tooltip=[
                        alt.Tooltip("bandgap_range:N", title="区间"),
                        alt.Tooltip("count:Q", title="数量")
                    ],
                )
                .properties(height=200)
                .configure_axis(gridColor="#f1f5f9", domainColor="#cbd5e0", labelFontSize=9, titleFontSize=10)
                .configure_view(strokeWidth=0)
            )

            st.altair_chart(chart, use_container_width=True)

            current_material = st.session_state.selected_material or "mp-1661648"

            st.markdown(
                f"""
                <div class="finding-box">
                    <div class="finding-title">🔍 关键发现</div>
                    <div class="finding-text">
                        带隙在 <span class="highlight">2–3 eV</span> 区间的材料数量最多。
                        对于材料 <span class="highlight">{current_material}</span>，该带隙范围通常意味着良好的电化学稳定性。
                    </div>
                </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

        # 卡片 3: 关键词分析
        with viz_col2:
            st.markdown(
                """
                <div class="card">
                    <div class="card-header">
                        <div class="card-number">3</div>
                        <div class="card-title">材料描述中的关键词频率分析</div>
                        <div class="card-icon">📌</div>
                    </div>
                """,
                unsafe_allow_html=True,
            )

            keywords_df = pd.DataFrame({
                "关键词": ["LiFePO4", "橄榄石", "正极", "锂离子", "稳定性"],
                "频率": [120, 85, 75, 60, 45],
            })

            keyword_chart = (
                alt.Chart(keywords_df)
                .mark_bar(color="#f59e0b", cornerRadiusTopLeft=6, cornerRadiusTopRight=6)
                .encode(
                    y=alt.Y("关键词:N", title="关键词", sort="-x", axis=alt.Axis(labelFontSize=10)),
                    x=alt.X("频率:Q", title="出现频率", axis=alt.Axis(labelFontSize=10)),
                    tooltip=["关键词", "频率"],
                )
                .properties(height=200)
                .configure_axis(gridColor="#f1f5f9", domainColor="#cbd5e0", labelFontSize=9, titleFontSize=10)
                .configure_view(strokeWidth=0)
            )

            st.altair_chart(keyword_chart, use_container_width=True)

            st.markdown(
                """
                <div class="finding-box">
                    <div class="finding-title">🔍 关键发现</div>
                    <div class="finding-text">
                        关键词 <span class="highlight">LiFePO4</span>、<span class="highlight">橄榄石</span> 
                        和 <span class="highlight">正极</span> 出现频率最高，体现了该材料的核心特征。
                    </div>
                </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

        # 第二行
        viz_col3, viz_col4 = st.columns(2, gap="medium")

        # 卡片 5: 地理分布（占位）
        with viz_col3:
            st.markdown(
                """
                <div class="card">
                    <div class="card-header">
                        <div class="card-number">5</div>
                        <div class="card-title">识别高风险区域的地理分布</div>
                        <div class="card-icon">📌</div>
                    </div>
                    <div style="background: #f8fafc; border-radius: 8px; padding: 3rem 1rem; text-align: center; color: #94a3b8;">
                        🗺️ 地图可视化占位区域
                    </div>
                    <div class="finding-box">
                        <div class="finding-title">🔍 关键发现</div>
                        <div class="finding-text">
                            空间分析揭示了 <span class="highlight">174 个实例</span> 在不同地理位置的分布模式。
                        </div>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

        # 卡片 11: 时序分析
        with viz_col4:
            st.markdown(
                """
                <div class="card">
                    <div class="card-header">
                        <div class="card-number">11</div>
                        <div class="card-title">检查特定标签随时间的变化</div>
                        <div class="card-icon">📌</div>
                    </div>
                """,
                unsafe_allow_html=True,
            )

            time_df = pd.DataFrame({
                "时间": ["05 PM", "06 PM", "07 PM", "08 PM", "09 PM"],
                "计数": [50, 120, 180, 140, 90],
            })

            time_chart = (
                alt.Chart(time_df)
                .mark_line(point=True, color="#ef4444", strokeWidth=3)
                .encode(
                    x=alt.X("时间:N", title="时间", axis=alt.Axis(labelFontSize=10)),
                    y=alt.Y("计数:Q", title="标签数量", axis=alt.Axis(labelFontSize=10)),
                    tooltip=["时间", "计数"],
                )
                .properties(height=180)
                .configure_axis(gridColor="#f1f5f9", domainColor="#cbd5e0", labelFontSize=9, titleFontSize=10)
                .configure_view(strokeWidth=0)
            )

            st.altair_chart(time_chart, use_container_width=True)

            st.markdown(
                """
                <div class="finding-box">
                    <div class="finding-title">🔍 关键发现</div>
                    <div class="finding-text">
                        在 <span class="highlight">07 PM</span> 观察到活动高峰，之后在 08 PM 后显著下降。
                    </div>
                </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

# ==================== C. 右栏：任务追溯 ====================
with col_right:
    st.markdown(
        """
        <div style="display: flex; align-items: center; gap: 0.6rem; margin-bottom: 0.8rem;">
            <span class="section-label label-c">C</span>
            <span style="font-size: 1rem; font-weight: 700; color: #1a202c;">任务追溯</span>
        </div>
        <div style="font-size: 0.8rem; color: #64748b; margin-bottom: 1rem;">
            🔄 任务流程 · <span class="badge badge-green">决策</span>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # 任务流
    if st.session_state.tasks:
        st.markdown('<div class="card"><div class="task-flow-container">', unsafe_allow_html=True)
        render_task_flow_simple(st.session_state.tasks)
        st.markdown("</div></div>", unsafe_allow_html=True)

        # 任务分解
        st.markdown(
            """
            <div class="card">
                <div style="display: flex; align-items: center; gap: 0.5rem; margin-bottom: 0.8rem;">
                    <div style="width: 24px; height: 24px; background: #ef4444; color: white; border-radius: 50%; 
                                display: flex; align-items: center; justify-content: center; font-size: 0.8rem; font-weight: 700;">a</div>
                    <div style="font-size: 0.9rem; font-weight: 600;">任务分解</div>
                </div>
            """,
            unsafe_allow_html=True,
        )

        decomposition_tasks = [
            {
                "title": "应用数据分段",
                "text": "分析关键事件前后的情感波动",
                "active": True,
            },
            {
                "title": "利用统计方法",
                "text": "识别情感数据分布中的模式",
                "active": False,
            },
            {
                "title": "实施高级技术",
                "text": "使用高级统计技术进行趋势分析",
                "active": False,
            },
        ]

        for task in decomposition_tasks:
            active_class = "active" if task["active"] else ""
            st.markdown(
                f"""
                <div class="decomposition-item {active_class}">
                    <div class="decomposition-title">✓ {task['title']}</div>
                    <div class="decomposition-text">{task['text']}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

        st.markdown("</div>", unsafe_allow_html=True)

    else:
        st.caption("📋 暂无任务流数据，请先在左侧开始对话")

    # 数据表
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

    if st.session_state.table_df is not None:
        st.markdown('<div class="card">', unsafe_allow_html=True)

        df_table = st.session_state.table_df.copy()

        # 材料选择
        mp_ids = list(df_table["材料ID"])
        default_material = (
            st.session_state.selected_material if st.session_state.selected_material in mp_ids else mp_ids[0]
        )
        selected_mp = st.selectbox(
            "🎯 选择关注的材料：",
            options=mp_ids,
            index=mp_ids.index(default_material),
            key="material_select",
        )
        st.session_state.selected_material = selected_mp

        # 表格
        styled = df_table.style.background_gradient(
            subset=["评分"],
            cmap="Blues",
            vmin=0,
            vmax=1,
        ).format({"评分": "{:.2f}"})

        st.dataframe(styled, use_container_width=True, height=220, hide_index=True)
        st.caption("💡 综合评分（0-1 范围，示例数据）")

        st.markdown("</div>", unsafe_allow_html=True)
    else:
        st.caption("📊 暂无数据")
