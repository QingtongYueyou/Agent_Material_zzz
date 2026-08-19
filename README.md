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
- 接收自然语言与可选文件，由 LLM 自动识别意图并选择 3DGS 或外部材料 MCP
- 通过统一 HTTP API 返回 MCP provider、tool 和可嵌入的 `render_url`
- 支持结构、DOS、XRD、相图、能带、有限元、三维模型和分子动力学等可视化
- 记录 3D 渲染和交互指标

## 目录

```text
api/                     FastAPI 后端入口、请求模型、JSON 序列化
frontend/                React + TypeScript 前端
core/                    材料分析业务核心
config/                  路径常量和环境变量
services/three_dgs_mcp/    3DGS MCP render_url 子服务与独立 viewer
demo/external_consumer/   仅通过 HTTP API 调用本项目的独立演示系统
cif_files/               CIF 缓存目录
static/splat_files/      3DGS/Spark 源资产、派生资产和 manifest
metrics/                 渲染/交互指标与分析脚本
tools/                   Spark 资产构建工具
tests/                   单元测试与 API/MCP 冒烟测试脚本
docs/                    资产管线等补充文档
```

## 环境变量

在项目根目录创建 `.env`，或使用系统环境变量：

```env
MP_API_KEY=your-materials-project-key

# 只需修改这一项即可切换 deepseek / minimax
LLM_PROVIDER=deepseek

DEEPSEEK_API_KEY=your-deepseek-key
DEEPSEEK_API_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL_ID=deepseek-v4-flash

MINIMAX_API_KEY=your-minimax-key
MINIMAX_API_BASE_URL=https://api.minimaxi.com/v1
MINIMAX_MODEL_ID=MiniMax-M3

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

`MP_API_KEY` 也兼容旧变量名 `MAPI_KEY`。MiniMax 配置继续兼容旧的 `POE_API_KEY` 和 `POE_API_BASE_URL`。

如需临时覆盖当前供应商的配置，可使用统一变量 `LLM_API_KEY`、`LLM_API_BASE_URL` 和 `LLM_MODEL_ID`。

生产环境中 `THREEDGS_PUBLIC_BASE_URL` 必须配置成浏览器可访问的真实地址，不能使用 `127.0.0.1`、`localhost` 或 `0.0.0.0`。

## 启动

### 一键启动开发服务

在项目根目录执行：

```powershell
.\start-dev.ps1
```

该脚本会启动 3DGS MCP（默认 `8090`）、Agent Material API（默认 `8080`）和主前端（默认 `5173`）。

如果 `8080` 已被其他程序或 WSL 端口转发占用，可以改用 `8081`：

```powershell
.\start-dev.ps1 -ApiPort 8081
```

也可以只启动 API：

```powershell
conda run -n agno-assist python -m uvicorn api.main:app --host 127.0.0.1 --port 8081
```

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

```powershell
conda run -n agno-assist python -m uvicorn api.main:app --host 127.0.0.1 --port 8080
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

### 独立外部调用 Demo

`demo/external_consumer` 是一个独立进程，不导入本项目的 `api`、`core` 或 `services` 模块，只通过 HTTP 调用 Agent Material。用户只输入自然语言并可选上传文件，LLM 自动完成文件理解、意图识别和 MCP 工具选择。

当 API 使用 `8081` 时，在项目根目录执行：

```powershell
.\demo\external_consumer\start.ps1 -UpstreamApi http://127.0.0.1:8081
```

浏览器访问 `http://127.0.0.1:3000`。

无文件的 3DGS 示例指令：

```text
请查询 LiFePO4（Materials Project 编号 mp-1661648）的晶体结构，并用三维高斯泼溅方式生成可交互可视化。请实际调用工具完成，不要只描述操作步骤。
```

上传文件后自动选择外部 MCP 的示例指令：

```text
请分析我上传的材料文件，识别它的数据类型，并自动选择最合适的可视化能力生成可交互结果。不要让我选择工具，也不要只返回文字说明。
```

## 后端接口

- `GET /health`：后端和资产管线状态
- `POST /api/chat/stream`：SSE 流式工作流事件
- `POST /api/chat`：自然语言 Agent 非流式接口，接收 `query` 和可选 `file_ids`
- `POST /api/files/upload`：上传材料文件并返回 `file_id`
- `GET /api/visualizations/capabilities`：查询统一可视化能力清单
- `POST /api/visualizations/render`：按明确意图调用统一可视化接口
- `GET /api/assets/splat/{filename}?quality=auto`：解析 3DGS/Spark 资产
- `GET /api/assets/pipeline`：查看 3D 资产管线状态
- `POST /api/mcp/render`：兼容旧版 CIF MCP 渲染接口
- `POST /api/3dgs/render`：向 3DGS MCP 服务请求独立 viewer 的 `render_url`
- `POST /api/metrics/render`：记录渲染指标
- `POST /api/metrics/interaction`：记录交互指标

## 统一可视化 API

推荐外部系统调用 `POST /api/chat`，让 LLM 根据自然语言和文件内容自动选择工具：

```json
{
  "query": "请分析上传的数据并自动选择最合适的 MCP 生成交互式可视化",
  "file_ids": ["file_xxx"]
}
```

最终事件中的 `artifacts` 会包含交付信息：

```json
{
  "intent": "xrd",
  "provider": "x-ray-mcp-server",
  "tool": "x_ray.xrd_file",
  "display": "iframe",
  "render_url": "http://example/viewer?render_id=..."
}
```

如果调用方已经明确知道可视化类型，可以直接使用确定性的 `POST /api/visualizations/render` 接口：

```json
{
  "intent": "dos",
  "input_type": "file",
  "file_id": "file_xxx"
}
```

当前能力包括：

| intent | 文件类型 | MCP 工具 |
|---|---|---|
| `3dgs` | 已注册 3DGS/Spark 资产 | `3dgs.create_render` |
| `structure` | CIF、XYZ、POSCAR、CELL、PDB | `fz.mol_file` |
| `dos` | DAT、TXT | `dos.dos_file` |
| `xrd` | DAT、TXT | `x_ray.xrd_file` |
| `binary_phase` | XLS、XLSX | `hot2.binary_xlsx_file` |
| `ternary_phase` | XLS、XLSX | `hot3.ternary_xlsx_file` |
| `band` | ZIP | `nb.band_zip_file` |
| `vtp` | VTP | `yxy.vtp_file` |
| `model` | STL、GLB | `hj_ol.model_file` |
| `molecular_dynamics` | DUMP、CFG、DATA、DAT、LMP、XYZ | `fzdl.model_file` |
| `phase_curve` | DAT、TXT | `xt.phase_curve_file` |
| `liquidus` / `liquidus_dual` / `liquidus_mass` | XLS、XLSX | `yxty3.*` |
| `isothermal` / `isothermal_dual` / `isothermal_mass` | XLS、XLSX | `dw3.*` |
| `vertical_section` | XLS、XLSX | `cz3.vertical_xlsx_file` |

相同扩展名可能对应不同能力，例如 TXT 可以是 DOS、XRD 或相曲线数据，XLSX 可以是多种热力学相图。因此 Agent 模式会结合自然语言和文件内容进行判断，而不是只根据扩展名路由。

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

```powershell
conda run -n agno-assist python -m compileall api core config
```

后端测试：

```powershell
conda run -n agno-assist pytest
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

### 外部 MCP 端到端冒烟测试

`tests/smoke_external_mcp_api.py` 会从 `docs/server_json/README.xlsx` 记录的官方地址下载测试文件到系统临时目录，然后验证“文件上传 → 统一 API → 外部 MCP → `render_url`”完整链路。样例不会写入 Git 仓库。

先启动 Agent Material API，然后执行全部 16 条非 CIF 路由：

```powershell
conda run -n agno-assist python tests\smoke_external_mcp_api.py --api-base http://127.0.0.1:8081
```

只测试指定能力：

```powershell
conda run -n agno-assist python tests\smoke_external_mcp_api.py `
  --api-base http://127.0.0.1:8081 `
  --intent dos `
  --intent xrd `
  --intent model
```

只下载官方样例，供浏览器 Demo 手动上传：

```powershell
conda run -n agno-assist python tests\smoke_external_mcp_api.py --download-only
```

默认样例目录：

```text
%TEMP%\agent-material-mcp-samples
```

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
