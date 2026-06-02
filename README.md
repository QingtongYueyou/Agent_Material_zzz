# Agent Material

Agent Material 是一个面向材料科学工作流的前后端分离应用。后端用 FastAPI 调度 LLM、Materials Project 查询、CIF 解析、3D Gaussian Splatting 资产解析、MCP 外部渲染和性能指标采集；前端用 React + TypeScript 提供对话、执行轨迹、3D 结构视图和材料数据图表。

当前主路径只保留 FastAPI + React。旧的 Streamlit 一体式入口和 Server-B Planner API 已移除。

## 功能

- 自然语言提问材料结构或筛选条件
- 通过 LLM function calling 调用 Materials Project 工具
- 保存并解析 CIF 文件
- 生成晶格参数、元素组成和模拟 XRD 数据
- 加载本地 Spark/3DGS 资产
- 通过 3DGS MCP 服务返回完整 `render_url` 并在 iframe 中展示独立 viewer
- 可选调用 MCP 服务生成外部可视化 iframe
- 记录 3D 渲染和交互指标

## 目录

```text
api/                     FastAPI 后端入口、请求模型、JSON 序列化
frontend/                React + TypeScript 前端
core/                    材料分析业务核心
config/                  路径常量和环境变量
services/three_dgs_mcp/    3DGS MCP render_url 子服务与独立 viewer
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

THREEDGS_MCP_ENABLED=true
THREEDGS_MCP_SERVER_URL=http://127.0.0.1:8090/mcp
THREEDGS_MCP_API_KEY=your-3dgs-mcp-key
THREEDGS_PUBLIC_BASE_URL=http://127.0.0.1:8090
THREEDGS_RENDER_TTL_SEC=600

SPARK_AUTO_INGEST=true
SPARK_AUTO_VARIANT=balanced
SPARK_ROOT=D:/tools/spark
```

`MP_API_KEY` 也兼容旧变量名 `MAPI_KEY`。

生产环境中 `THREEDGS_PUBLIC_BASE_URL` 必须配置成浏览器可访问的真实地址，不能使用 `127.0.0.1`、`localhost` 或 `0.0.0.0`。

## 启动

### 3DGS MCP viewer

首次使用或 viewer 代码更新后，先构建独立 3DGS viewer：

```bash
cd services/three_dgs_mcp/viewer
npm install
npm run build
```

启动 3DGS MCP 服务：

```bash
conda activate agno-assist
uvicorn services.three_dgs_mcp.server:app --host 127.0.0.1 --port 8090
```

健康检查：

```bash
curl http://127.0.0.1:8090/health
```

### 主后端

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

3DGS 视图默认使用 MCP `render_url` 模式。如果需要回退到前端内置 Spark viewer：

```bash
set VITE_3DGS_RENDER_MODE=local
```

## 后端接口

- `GET /health`：后端和资产管线状态
- `POST /api/chat/stream`：SSE 流式工作流事件
- `POST /api/chat`：非流式调试接口
- `GET /api/assets/splat/{filename}?quality=auto`：解析 3DGS/Spark 资产
- `GET /api/assets/pipeline`：查看 3D 资产管线状态
- `POST /api/mcp/render`：对指定 CIF 请求 MCP 外部渲染
- `POST /api/3dgs/render`：向 3DGS MCP 服务请求独立 viewer 的 `render_url`
- `POST /api/metrics/render`：记录渲染指标
- `POST /api/metrics/interaction`：记录交互指标

## 3DGS MCP 接口

3DGS MCP 服务暴露以下路径：

- `POST /mcp`：JSON-RPC 入口，支持 `tools/list` 和 `tools/call`。
- `GET /viewer/sessions/{session_id}`：独立 3DGS viewer 页面。
- `GET /viewer/sessions/{session_id}/config`：viewer 会话配置。
- `GET /viewer/sessions/{session_id}/assets/{relative_path}?token=...`：按 viewer session 和 token 安全托管 `.rad/.radc/.ply/.splat/.spz/.ksplat` 资源。

核心工具：

```json
{
  "name": "3dgs.create_render",
  "arguments": {
    "filename": "mp-1661648_LiFePO4.cif",
    "quality": "auto",
    "ttl_sec": 600
  }
}
```

返回示例：

```json
{
  "ok": true,
  "source": "3dgs:mcp",
  "session_id": "...",
  "render_url": "http://127.0.0.1:8090/viewer/sessions/...?token=...",
  "expires_at": 1780200600,
  "asset": {
    "model_url": "http://127.0.0.1:8090/viewer/sessions/.../assets/derived/.../model.rad?token=...",
    "enable_lod": true,
    "enable_paged": true
  }
}
```

如果配置了 `THREEDGS_MCP_API_KEY`，客户端必须在请求头中携带 `Authorization: Bearer <THREEDGS_MCP_API_KEY>`；旧的 `visualization-api-key` 仅保留兼容。

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
7. React 更新回答、执行轨迹和图表。
8. MCP 3DGS 模式下，前端调用 `POST /api/3dgs/render`，主后端转发到 `services.three_dgs_mcp.server`。
9. 3DGS MCP 服务解析资产、创建持久化 session，并返回独立 viewer 的 `render_url`。
10. React 在 iframe 中展示 `/viewer/sessions/{session_id}`。

## 验证

后端基础验证：

```bash
python -m compileall api core config
```

前端构建：

```bash
npm --prefix frontend run build
```

3DGS viewer 构建：

```bash
npm --prefix services/three_dgs_mcp/viewer run build
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

本地 fallback 模式下，前端调用 `GET /api/assets/splat/{filename}`，由 `core/splat_assets.py` 按 manifest 优先解析。

MCP render_url 模式下，主前端调用 `POST /api/3dgs/render`，3DGS MCP 服务复用同一套资产解析逻辑并生成独立 viewer session。session 会持久化到已忽略的 `static/splat_files/_pipeline/3dgs_sessions.json`，用于服务重启或多进程场景下恢复 `/viewer/sessions/{session_id}/config`。

## 维护约定

- 后端接口不要直接返回 Pandas DataFrame，统一走 `api/serialization.py`。
- 不再恢复 Streamlit 入口或 Planner API 路径。
- 大文件和生成产物不要提交：`frontend/node_modules/`、`frontend/dist/`、`frontend/test-results/`、`services/three_dgs_mcp/viewer/node_modules/`、`services/three_dgs_mcp/viewer/dist/`、CIF 缓存、metrics CSV、3DGS session JSON 和派生 3D 资产默认忽略。
