# Agent Material

Agent Material 是一个面向材料科学工作流的前后端分离应用。后端用 FastAPI 调度 LLM、Materials Project 查询、CIF 解析、3D Gaussian Splatting 资产解析、MCP 外部渲染和性能指标采集；前端用 React + TypeScript 提供对话、执行轨迹、3D 结构视图和材料数据图表。

当前主路径只保留 FastAPI + React。旧的 Streamlit 一体式入口和 Server-B Planner API 已移除。

## 功能

- 自然语言提问材料结构或筛选条件
- 通过 LLM function calling 调用 Materials Project 工具
- 保存并解析 CIF 文件
- 生成晶格参数、元素组成和模拟 XRD 数据
- 加载本地 Spark/3DGS 资产
- 可选调用 MCP 服务生成外部可视化 iframe
- 记录 3D 渲染和交互指标

## 目录

```text
api/                     FastAPI 后端入口、请求模型、JSON 序列化
frontend/                React + TypeScript 前端
core/                    材料分析业务核心
config/                  路径常量和环境变量
cif_files/               CIF 缓存目录
static/splat_files/      3DGS/Spark 源资产、派生资产和 manifest
metrics/                 渲染/交互指标与分析脚本
tools/                   Spark 资产构建工具
docs/                    资产管线等补充文档
```

## 环境变量

在项目根目录创建 `.env`，或使用系统环境变量：

```env
MP_API_KEY=your-materials-project-key
POE_API_KEY=your-llm-key
POE_API_BASE_URL=https://api.poe.com/v1
LLM_MODEL_ID=GPT-4o
LLM_TIMEOUT_SEC=45

MCP_ENABLED=true
MCP_SERVER_URL=http://example/mcp
MCP_API_KEY=your-mcp-key
MCP_TIMEOUT_SEC=60
MCP_RENDER_TTL_SEC=600

SPARK_AUTO_INGEST=true
SPARK_AUTO_VARIANT=balanced
SPARK_ROOT=D:/tools/spark
```

`MP_API_KEY` 也兼容旧变量名 `MAPI_KEY`。

## 启动

### 后端

```bash
conda activate agno-assist
uvicorn api.main:app --host 127.0.0.1 --port 8080
```

健康检查：

```bash
curl http://127.0.0.1:8080/health
```

### 前端

```bash
cd frontend
npm install
npm run dev
```

默认访问：

```text
http://127.0.0.1:5173
```

Vite 开发服务器会把 `/api`、`/health`、`/static` 代理到 `http://127.0.0.1:8080`。如果需要指向其他后端地址：

```bash
set VITE_API_BASE_URL=http://127.0.0.1:8080
```

## 后端接口

- `GET /health`：后端和资产管线状态
- `POST /api/chat/stream`：SSE 流式工作流事件
- `POST /api/chat`：非流式调试接口
- `GET /api/assets/splat/{filename}?quality=auto`：解析 3DGS/Spark 资产
- `GET /api/assets/pipeline`：查看 3D 资产管线状态
- `POST /api/mcp/render`：对指定 CIF 请求 MCP 外部渲染
- `POST /api/metrics/render`：记录渲染指标
- `POST /api/metrics/interaction`：记录交互指标

`/api/chat/stream` 事件示例：

```json
{"type":"step_start","step":"function_calling"}
{"type":"step_end","step":"get_mp_structure","status":"success","latency_ms":1234}
{"type":"final","answer":"...","viz":{"filename":"mp-1661648_LiFePO4.cif","lattice":[],"composition":[],"xrd":[]}}
```

## 主流程

1. React 前端向 `POST /api/chat/stream` 发送问题。
2. `api/main.py` 调用 `WorkflowOrchestrator.run_stream()`。
3. `core/workflow.py` 通过 LLM function calling 调用 `core/tools.py`。
4. `core/tools.py` 查询 Materials Project 并写入 CIF。
5. `core/processor.py` 解析 CIF，生成晶格、组成和 XRD 数据。
6. `api/serialization.py` 将 Python/Pandas 对象转成前端 JSON。
7. React 更新回答、执行轨迹、图表、3DGS 视图和 MCP 视图。

## 验证

后端基础验证：

```bash
python -m compileall api core config
```

前端构建：

```bash
npm --prefix frontend run build
```

浏览器冒烟测试：

```bash
npm --prefix frontend run visual:smoke
```

`visual:smoke` 使用本机 Microsoft Edge 检查桌面布局、移动布局和真实 3D canvas 非空渲染。截图会写入已忽略的 `frontend/test-results/`。

## 3D 资产

3DGS/Spark 资产放在 `static/splat_files/`：

- `source/`：原始 `.ply/.spz/.splat/.ksplat`
- `derived/<asset-id>/`：构建后的 `.rad/.radc` 与 manifest
- `_pipeline/`：后台同步状态
- `_bounds/`：PLY bounds 缓存

前端不直接猜路径，而是调用 `GET /api/assets/splat/{filename}`，由 `core/splat_assets.py` 按 manifest 优先解析。

## 维护约定

- 后端接口不要直接返回 Pandas DataFrame，统一走 `api/serialization.py`。
- 不再恢复 Streamlit 入口或 Planner API 路径。
- 大文件和生成产物不要提交：`frontend/node_modules/`、`frontend/dist/`、`frontend/test-results/`、CIF 缓存、metrics CSV 和派生 3D 资产默认忽略。
