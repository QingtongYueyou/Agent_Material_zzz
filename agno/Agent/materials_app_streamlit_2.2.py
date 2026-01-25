# materials_app_streamlit.py

import streamlit as st
import pandas as pd
import altair as alt
import os
import glob

# === 强制修复路径问题 ===
# 1. 获取当前脚本 (materials_app_streamlit.py) 所在的绝对目录
# 结果应该是 .../Material_visualization/agno/Agent
CURRENT_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# 2. 拼接出正确的 cif_files 路径
# 结果应该是 .../Material_visualization/agno/Agent/cif_files
CIF_DIR_FIXED = os.path.join(CURRENT_SCRIPT_DIR, "cif_files")

# 3. 自动创建文件夹（以防万一）
os.makedirs(CIF_DIR_FIXED, exist_ok=True)

# ==========================================
# === 新增: 引入 pymatgen 用于结构分析 ===
try:
    from pymatgen.core import Structure
    from pymatgen.analysis.diffraction.xrd import XRDCalculator

    HAS_PYMATGEN = True
except ImportError:
    HAS_PYMATGEN = False

try:
    import graphviz

    HAS_GRAPHVIZ = True
except ImportError:
    HAS_GRAPHVIZ = False

from material_chatbot import materials_agent, CIF_DIR  # <--- 导入共享的路径变量

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

if "viz_data" not in st.session_state:
    st.session_state.viz_data = None  # 存储真实的结构可视化数据

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

# def build_example_tasks(question: str):
#     short_q = question[:25] + ("…" if len(question) > 25 else "")
#     return [
#         {"id": "T1", "label": f"理解问题：{short_q}", "status": "done", "progress": "100%"},
#         {"id": "T2", "label": "从 Materials Project 获取结构数据", "status": "done", "progress": "100%"},
#         {"id": "T3", "label": "分析晶体结构与配位环境", "status": "running", "progress": "60%"},
#         {"id": "T4", "label": "生成可视化与结构总结", "status": "pending", "progress": "0%"},
#     ]

# ------------------ 辅助函数 (修改部分) ------------------

def generate_real_tasks():
    tasks = []

    # 获取是否正在处理的标记
    is_processing = st.session_state.get("processing", False)

    # ================== T1: 意图识别 ==================
    last_q = st.session_state.get("last_question", "")
    has_question = bool(last_q)

    tasks.append({
        "id": "T1",
        "label": f"意图识别: {last_q[:15]}..." if has_question else "等待用户提问...",
        "status": "done" if has_question else "pending",
        "progress": "100%" if has_question else "0%"
    })

    # ================== T2: 数据获取 ==================
    viz_data = st.session_state.get("viz_data")
    has_data = viz_data is not None

    # 逻辑升级：如果没数据，但在处理中，就是 Running
    if has_data:
        t2_status = "done"
        t2_progress = "100%"
    elif is_processing:
        t2_status = "running"
        t2_progress = "45%"  # 给个中间值
    else:
        t2_status = "pending"
        t2_progress = "0%"

    tasks.append({
        "id": "T2",
        "label": "Materials Project 接口调用与落地",
        "status": t2_status,
        "progress": t2_progress
    })

    # ================== T3: Agent 推理 ==================
    messages = st.session_state.get("messages", [])
    has_reply = False
    # 检查是否有助手回复（且不在处理中，或者有新的回复）
    # 简单判断：如果是刚提问还在处理，肯定没生成完
    if messages and messages[-1]["role"] == "assistant" and not is_processing:
        has_reply = True

    # 逻辑升级：如果数据下完了(T2完了)但在处理，那T3就是Running；或者 T2 在跑，T3 等待
    if has_reply:
        t3_status = "done"
        t3_progress = "100%"
    elif is_processing:
        # 如果 T2 还在跑，T3 是 pending；如果模拟 T2 很快，这里也可以设为 running
        # 为了视觉效果，我们让它显示 Pending 或 Running 均可，这里设为 Pending 等 T2
        t3_status = "running" if has_data else "pending"
        t3_progress = "20%"
    else:
        t3_status = "pending"
        t3_progress = "0%"

    tasks.append({
        "id": "T3",
        "label": "晶体结构分析与 Agent 推理",
        "status": t3_status,
        "progress": t3_progress
    })

    # ================== T4: 可视化 ==================
    # (保持原逻辑，加上 processing 判断)
    t4_status = "pending"
    t4_progress = "0%"

    if has_data and not is_processing:
        if not viz_data['xrd_df'].empty:
            t4_status = "done"
            t4_progress = "100%"
        else:
            t4_status = "running"
            t4_progress = "50%"

    tasks.append({
        "id": "T4",
        "label": "可视化图表渲染 (Lattice/XRD)",
        "status": t4_status,
        "progress": t4_progress
    })

    return tasks


# 保留渲染函数不变

def render_task_flow_simple(tasks):
    """简化的任务流展示 """
    for i, t in enumerate(tasks):
        icon_map = {"done": "✓", "running": "⟳", "pending": "○"}
        status_icon = icon_map.get(t["status"], "○")

        status_class = t["status"]

        # 获取当前选中的任务ID，安全获取
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


# === 新增: 获取并处理 CIF 数据的函数 ===
def get_latest_cif_info(cif_dir=CIF_DIR_FIXED):
    """
    获取目录下最新的 CIF 文件，解析结构并返回用于绘图的 DataFrame
    """
    print("-" * 50)
    print(f"DEBUG: 脚本所在位置: {CURRENT_SCRIPT_DIR}")
    print(f"DEBUG: 正在扫描目标: {cif_dir}")

    if not HAS_PYMATGEN:
        print("DEBUG: 缺少 pymatgen")
        return None, None, None, None

    # 1. 扫描文件
    search_pattern = os.path.join(cif_dir, "*.cif")
    list_of_files = glob.glob(search_pattern)

    print(f"DEBUG: 找到文件数量: {len(list_of_files)}")

    if not list_of_files:
        return None, None, None, None

    # 找到最新的文件
    latest_file = max(list_of_files, key=os.path.getctime)
    filename = os.path.basename(latest_file)
    print(f"DEBUG: 成功锁定最新文件: {filename}")

    # 2. 使用 pymatgen 加载结构
    try:
        structure = Structure.from_file(latest_file)
    except Exception as e:
        print(f"DEBUG: 文件解析失败: {e}")
        return None, None, None, None

    # --- 数据准备 A: 晶格参数 ---
    lattice = structure.lattice
    lattice_df = pd.DataFrame({
        "Parameter": ["a", "b", "c"],
        "Value": [lattice.a, lattice.b, lattice.c],
        "Unit": ["Å", "Å", "Å"]
    })

    # --- 数据准备 B: 元素组分 ---
    comp = structure.composition
    element_data = []
    # 修改点：element 已经是字符串，直接使用
    for element, amount in comp.get_el_amt_dict().items():
        element_data.append({
            "Element": element,  # <--- 这里的 element 已经是字符串了
            "Count": amount,
            "Fraction": comp.get_atomic_fraction(element)
        })

    # === 关键修复：确保这行代码存在 ===
    comp_df = pd.DataFrame(element_data)

    # --- 数据准备 C: 模拟 XRD ---
    try:
        xrd_calc = XRDCalculator(wavelength="CuKa")
        pattern = xrd_calc.get_pattern(structure)
        xrd_data = []
        for theta, intensity, hkls in zip(pattern.x, pattern.y, pattern.hkls):
            if theta > 70: break
            hkl_str = str(hkls[0]['hkl'])
            xrd_data.append({"2Theta": theta, "Intensity": intensity, "HKL": hkl_str})
        xrd_df = pd.DataFrame(xrd_data)
    except Exception:
        xrd_df = pd.DataFrame()

    return filename, lattice_df, comp_df, xrd_df


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
                <div style="font-size: 0.65rem; margin-top: 0.5rem; color: #cbd5e0;">支持根据 MP-ID 或化学式生成结构图表</div>
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
        # 1. 记录问题
        st.session_state.last_question = user_input
        st.session_state.messages.append({"role": "user", "content": user_input})

        # 2. 标记正在处理
        st.session_state.processing = True

        # 3. 立即刷新！(关键)
        # 这样页面会重新渲染，右边的 Tasks 就会读取 processing=True 变成转圈状态
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
            📊 结构数据视图 · <span class="badge badge-blue">动态生成</span>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # 检查是否有 pymatgen
    if not HAS_PYMATGEN:
        st.error("⚠️ 未检测到 `pymatgen` 库。可视化功能受限。请运行 `pip install pymatgen`。")

    # 检查是否有可视化数据
    if st.session_state.viz_data is None:
        st.info("💡 请在左侧输入材料名称（如 LiFePO4），AI 将获取结构并在此生成分析图表。")

        # 显示一个空的占位符，保持布局美观
        st.markdown(
            """
            <div class="card" style="height: 200px; display: flex; align-items: center; justify-content: center; color: #cbd5e0;">
                等待数据输入...
            </div>
            """,
            unsafe_allow_html=True
        )
    else:
        # 获取数据
        viz = st.session_state.viz_data
        filename = viz["filename"]

        # === 第一行：晶格与组分 ===
        viz_col1, viz_col2 = st.columns(2, gap="medium")

        # --- 卡片 1: 晶胞参数 ---
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
                alt.Chart(viz['lattice_df'])
                .mark_bar(color="#667eea", cornerRadiusTopLeft=6, cornerRadiusTopRight=6)
                .encode(
                    x=alt.X('Parameter:N', title=None,
                            axis=alt.Axis(labelAngle=0, labelFontSize=11, labelFontWeight="bold")),
                    y=alt.Y('Value:Q', title='长度 (Å)', axis=alt.Axis(labelFontSize=10)),
                    color=alt.Color('Parameter', legend=None, scale=alt.Scale(scheme="tableau10")),
                    tooltip=['Parameter', 'Value', 'Unit']
                )
                .properties(height=180)
                .configure_axis(gridColor="#f1f5f9", domainColor="#cbd5e0")
                .configure_view(strokeWidth=0)
            )

            st.altair_chart(chart_lat, use_container_width=True)

            # 动态计算最大轴
            max_axis = viz['lattice_df'].loc[viz['lattice_df']['Value'].idxmax()]

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

        # --- 卡片 2: 元素组分 ---
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

            base = alt.Chart(viz['comp_df']).encode(
                theta=alt.Theta("Count", stack=True)
            )

            pie = base.mark_arc(innerRadius=50, outerRadius=80).encode(
                color=alt.Color("Element", scale=alt.Scale(scheme="set2")),
                order=alt.Order("Count", sort="descending"),
                tooltip=["Element", "Count", alt.Tooltip("Fraction", format=".1%")]
            ).properties(height=180)

            # 叠加文字
            text = base.mark_text(radius=90).encode(
                text=alt.Text("Element"),
                order=alt.Order("Count", sort="descending"),
                color=alt.value("#4a5568")
            )

            st.altair_chart(pie + text, use_container_width=True)

            elements_str = ", ".join(viz['comp_df']['Element'].tolist())
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

        # === 第二行：XRD 模拟 ===
        # 卡片 3: 模拟 XRD
        st.markdown("<br>", unsafe_allow_html=True)  # 间距
        st.markdown(
            f"""
            <div class="card">
                <div class="card-header">
                    <div class="card-number">3</div>
                    <div class="card-title">模拟 XRD 图谱 (Cu-Kα, λ=1.5406 Å)</div>
                    <div class="card-icon">📉</div>
                </div>
            """,
            unsafe_allow_html=True,
        )

        if not viz['xrd_df'].empty:
            chart_xrd = (
                alt.Chart(viz['xrd_df'])
                .mark_rule(size=2, color="#f59e0b")
                .encode(
                    x=alt.X('2Theta:Q', title='2θ (Degrees)', scale=alt.Scale(zero=False)),
                    y=alt.Y('Intensity:Q', title='Intensity (%)'),
                    tooltip=['2Theta', 'Intensity', 'HKL']
                )
                .properties(height=220)
                .configure_axis(gridColor="#f1f5f9", domainColor="#cbd5e0")
                .configure_view(strokeWidth=0)
            )
            st.altair_chart(chart_xrd, use_container_width=True)

            strongest_peak = viz['xrd_df'].loc[viz['xrd_df']['Intensity'].idxmax()]
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
            unsafe_allow_html=True)

# ==================== C. 右栏：任务追溯 ====================
with col_right:
    st.markdown(
        """
        <div style="display: flex; align-items: center; gap: 0.6rem; margin-bottom: 0.8rem;">
            <span class="section-label label-c">C</span>
            <span style="font-size: 1rem; font-weight: 700; color: #1a202c;">任务追溯</span>
        </div>
        <div style="font-size: 0.8rem; color: #64748b; margin-bottom: 1rem;">
            🔄 任务流程 · <span class="badge badge-green">状态机实时监控</span>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # === 核心修改：获取基于真实产物的任务状态 ===
    # 这里调用刚才定义的新函数，不再读 session_state 中的死数据
    current_tasks = generate_real_tasks()

    # 自动计算当前应该高亮的任务 ID (逻辑：找第一个状态是 running 的，或者最后一个状态是 done 的)
    active_task_id = None
    # 优先找正在运行的
    for t in current_tasks:
        if t['status'] == 'running':
            active_task_id = t['id']
            break
    # 没找到 running，找最后一个 done 的
    if not active_task_id:
        for t in reversed(current_tasks):
            if t['status'] == 'done':
                active_task_id = t['id']
                break

    # 只有当有任务数据且至少有一个任务开始时才显示
    if current_tasks and current_tasks[0]['status'] != 'pending':
        # 因为 render_task_flow_simple 需要用到 session_state.selected_task_id 来高亮
        # 我们临时赋值给它，或者你可以修改 render_task_flow_simple 函数让它接受 active_id 参数
        # 为了最小化修改，这里用 session_state 传参:
        st.session_state.selected_task_id = active_task_id

        st.markdown('<div class="card"><div class="task-flow-container">', unsafe_allow_html=True)
        render_task_flow_simple(current_tasks)
        st.markdown("</div></div>", unsafe_allow_html=True)

        # --- 任务分解 (Agent Decomposition) ---
        # 只有当 T3 (Agent推理) 完成或进行中时才显示这个细节
        t3_status = next((t['status'] for t in current_tasks if t['id'] == 'T3'), 'pending')

        if t3_status in ['done', 'running']:
            st.markdown(
                """
                <div class="card">
                    <div style="display: flex; align-items: center; gap: 0.5rem; margin-bottom: 0.8rem;">
                        <div style="width: 24px; height: 24px; background: #ef4444; color: white; border-radius: 50%; 
                                    display: flex; align-items: center; justify-content: center; font-size: 0.8rem; font-weight: 700;">a</div>
                        <div style="font-size: 0.9rem; font-weight: 600;">Agent 执行细节</div>
                    </div>
                """,
                unsafe_allow_html=True,
            )

            decomposition_tasks = [
                {
                    "title": "意图识别",
                    "text": f"用户意图: {st.session_state.last_question[:10]}...",
                    "active": True,
                },
                {
                    "title": "API 调用",
                    "text": "Materials Project 接口响应成功",
                    "active": st.session_state.get("viz_data") is not None,
                },
                {
                    "title": "文件落地",
                    "text": f"CIF: {st.session_state.viz_data['filename']}" if st.session_state.get(
                        "viz_data") else "等待下载...",
                    "active": st.session_state.get("viz_data") is not None,
                },
            ]

            for task in decomposition_tasks:
                active_class = "active" if task["active"] else ""
                icon = "✓" if task["active"] else "○"
                st.markdown(
                    f"""
                    <div class="decomposition-item {active_class}">
                        <div class="decomposition-title">{icon} {task['title']}</div>
                        <div class="decomposition-text">{task['text']}</div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

            st.markdown("</div>", unsafe_allow_html=True)

    else:
        # 初始状态
        st.markdown(
            """
            <div class="card" style="text-align: center; padding: 2rem 1rem; color: #94a3b8;">
                <div>⏳</div>
                <div style="font-size: 0.85rem; margin-top: 0.5rem;">等待任务启动</div>
            </div>
            """,
            unsafe_allow_html=True
        )

    # --- 数据表部分 (Data Traceability) ---
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

        # 展示晶格数据的原始表格
        df_table = st.session_state.viz_data['lattice_df']
        st.dataframe(df_table, use_container_width=True, hide_index=True)

        # 如果 XRD 没算出来，提示一下
        if st.session_state.viz_data['xrd_df'].empty:
            st.warning("⚠️ 提示: 检测到晶格数据，但未生成 XRD 图谱 (可能是非周期性结构)")

        st.markdown("</div>", unsafe_allow_html=True)
    else:
        st.caption("📊 暂无数据，请在左侧开始对话")

# ==================== 最后的执行逻辑 ====================
# 检查是否有正在进行的任务
if st.session_state.get("processing", False):

    # 把 Spinner 放在左栏的对话框下面，体验更好
    with col_left:
        with st.spinner("🔍 AI 正在分析并获取结构数据..."):
            try:
                # 获取最近的问题
                user_question = st.session_state.last_question

                # 1. 运行 Agent (这里是最耗时的阻塞操作)
                result = materials_agent.run(user_question)
                reply_text = getattr(result, "content", str(result))

                # 2. 存入消息历史
                st.session_state.messages.append({"role": "assistant", "content": reply_text})

                # 3. 获取新生成的数据
                cif_name, lat_df, el_df, xrd_df = get_latest_cif_info()

                if cif_name:
                    st.session_state.viz_data = {
                        "filename": cif_name,
                        "lattice_df": lat_df,
                        "comp_df": el_df,
                        "xrd_df": xrd_df
                    }
            except Exception as e:
                st.error(f"运行出错: {e}")
            finally:
                # 4. 任务结束，关闭 processing 标记
                st.session_state.processing = False

                # 5. 再刷新一次，显示最终结果(100%)
                st.rerun()

# ------------------ 调试工具 ------------------
with st.sidebar:
    st.divider()
    st.header("🔧 调试面板")
    st.write(f"**当前扫描路径:** `{CIF_DIR_FIXED}`")

    if os.path.exists(CIF_DIR_FIXED):
        files = os.listdir(CIF_DIR_FIXED)
        st.write(f"**文件数量:** {len(files)}")
        if len(files) > 0:
            st.write("**最新文件:**")
            st.code(files[-1])
        else:
            st.error("文件夹为空！Agent 没有生成文件。")
            st.info("可能原因：API Key 无效，或者 Agent 没有调用下载工具。")
    else:
        st.error("文件夹不存在！")

    if "viz_data" in st.session_state and st.session_state.viz_data:
        st.success("✅ viz_data 已加载")
    else:
        st.warning("⏳ viz_data 为空")