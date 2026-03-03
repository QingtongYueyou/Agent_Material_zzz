from __future__ import annotations

import streamlit as st


def apply_styles() -> None:
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

        /* 右栏（任务追踪）*/
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
            max-width: 88% !important;
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
            max-width: 95% !important;
            font-size: 0.85rem !important;
            line-height: 1.5 !important;
            word-wrap: break-word;
            overflow-x: auto !important;
        }

        /* 消息时间戳（如需） */
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
            font-size: 0.9rem !important;
            padding: 0.85rem 1.3rem !important;
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
