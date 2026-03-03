# MaterialProject

## 运行

```bash
streamlit run app.py
```

## 模块结构

### 入口与配置
- `app.py`
  - 设置 Streamlit 页面参数与初始化状态
  - 组合三栏布局并调用各 UI 组件
  - 负责对话触发、流式输出与数据刷新
- `config/settings.py`
  - 统一加载 `.env` 配置
  - 管理路径常量（`cif_files/`, `static/`, `splat_files/`）
  - 初始化目录并暴露 API Key

### 核心逻辑
- `core/agent.py`
  - 定义 Agno Agent（模型、工具、提示词）
  - 绑定材料检索/结构解析工具
- `core/tools.py`
  - `get_mp_structure`：从 Materials Project 拉取结构并保存 CIF
  - `search_materials_by_criteria`：按条件检索材料并返回 JSON
- `core/processor.py`
  - 从 CIF 解析晶格与组分
  - 生成 XRD 模拟数据
  - 负责返回可视化所需的 DataFrame

### UI 组件
- `ui/styles.py`
  - 全局 CSS 样式与主题定义
- `ui/chat.py`
  - 左侧聊天面板（历史消息 + 输入框）
- `ui/visualization.py`
  - 中栏可视化：Altair 图表 + 3DGS 视图
  - 内置静态资源服务（CORS）以加载 splat 模型
- `ui/components.py`
  - 顶部栏组件
  - 任务流与 Agent 日志渲染
  - 右侧数据追溯与调试侧栏

## 说明

- `.env` 存放 API Key，建议仅本地保存
- CIF 缓存目录：`cif_files/`
- 3D splat 资源：`static/splat_files/`
