# MCP 工具扩展实施计划

> 修订日期: 2026-07-01
> 当前目标: 基于现有 FastAPI + React 项目，把远程 MCP 可视化服务接入为受控、可扩展的系统工具；第一版先跑通“上传文件 -> LLM 意图识别 -> 后端白名单路由 -> MCP tools/call -> artifacts[] -> 前端 iframe 展示”的最小闭环。

---

## 1. 当前项目现状

这份计划以当前仓库代码为准，而不是从零设计。

### 1.1 后端现状

- `api/schemas.py`
  - `ChatRequest` 当前只有 `query`。
  - `McpRenderRequest` 当前只有 `cif_path`。
- `api/main.py`
  - `/api/chat/stream` 只把 `request.query` 传给 `WorkflowOrchestrator.run_stream()`。
  - `/api/mcp/render` 只支持 CIF 路径，并调用 `core.mcp_client.process_file()`。
  - `/api/3dgs/render` 已有独立 3DGS MCP 专线。
- `config/settings.py`
  - 当前只有单个 `MCP_SERVER_URL` / `MCP_API_KEY`。
  - 没有 `MCP_CONFIG_DIR`、`MCP_UPLOAD_DIR`、`MCP_TOOL_GATEWAY_ENABLED` 等通用网关配置。
- `core/mcp_client.py`
  - 当前是旧通用 MCP 客户端。
  - 固定调用 `fz.process_file` / `fz.process_http`。
  - 只面向单个 `MCP_SERVER_URL`。
  - 已有可复用能力: plain JSON / SSE JSON 解析、`render_url` 提取、TTL freshness 判断。
- `core/3dgs_mcp_client.py`
  - 已支持 MCP initialize、`Mcp-Session-Id`、initialized notification、session 失效重试、`structuredContent` 提取。
  - 新通用 gateway 应吸收这里的 sessionful MCP 处理经验，而不是只复制旧 `mcp_client.py`。
- `core/tools.py`
  - 当前 OpenAI tools 只有 `get_mp_structure` 和 `search_materials_by_criteria`。
  - 没有 `render_with_mcp`。
- `core/workflow.py`
  - 当前 workflow 只围绕 Materials Project 查询、CIF 解析、单个 `viz_result`。
  - `SYSTEM_PROMPT` 尚未约束 MCP 可视化工具调用。
  - final SSE 事件只返回 `viz`，没有 `artifacts`。
- `core/workflow_types.py`
  - `WorkflowContext` 当前没有 `file_ids`、`uploaded_files`、`artifacts`。
- `api/serialization.py`
  - 当前只特殊序列化 `viz`，没有 artifact 序列化。

### 1.2 前端现状

- `frontend/src/api.ts`
  - `streamChat(query)` 只发送 `{ query }`。
  - 没有上传 API。
- `frontend/src/types.ts`
  - `WorkflowEvent` 没有 `artifacts`。
  - 没有 `UploadedFile` / `Artifact` 类型。
- `frontend/src/App.tsx`
  - 只维护单个 `viz` 状态。
  - final 事件只读取 `event.viz`。
- `frontend/src/components/ChatPanel.tsx`
  - 没有附件上传和附件 chip。
- `frontend/src/components/VisualizationPanel.tsx`
  - 主要围绕单个 `VizData` 和 3DGS viewer 展示。
- `frontend/src/components/McpViewer.tsx`
  - 已有 iframe、缓存、过期刷新、健康检查、错误展示逻辑。
  - 后续 `McpIframeArtifact` 应优先复用这些状态管理思路。

### 1.3 MCP server 配置现状

当前仓库已有:

```text
docs/server_json/
  cz3-mcp-server.json
  dos-mcp-server.json
  dw3-mcp-server.json
  fz-mcp-server.json
  fzdl-mcp-server.json
  hj-ol-mcp-server.json
  hot2-mcp-server.json
  hot3-mcp-server.json
  nb-mcp-server.json
  x-ray-mcp-server.json
  xt-mcp-server.json
  yxty3-mcp-server.json
  yxy-mcp-server.json
```

因此计划不再假设唯一配置目录是:

```text
C:/Users/wyfz/OneDrive/Desktop/server_json/
```

新的约定:

- 开发默认可用 `docs/server_json`。
- 生产和个人环境用 `.env` 的 `MCP_CONFIG_DIR` 覆盖。
- `docs/server_json` 只作为示例或开发配置，不应提交真实生产密钥。

### 1.4 第一版不做的事

第一版只追求最小闭环，不做以下能力:

- PDF/DOC/JPG/PNG 内容理解。
- 从论文图或截图反推曲线数据。
- URL 输入和 SSRF 防护完整闭环。
- 静态截图 `image_url`。
- 对外 `/v1/render-jobs` 异步任务 API。
- SDK。
- 让 LLM 直接看到和选择全部 MCP server/tool。

这些放到 Phase 2 或 Phase 3。

---

## 2. 总体目标

用户只需要上传文件并用自然语言描述目标:

```text
把这个 DOS 数据画出来。
把这两个 txt 分别按 DOS 和 XRD 可视化。
这个 Excel 是二元相图数据，帮我生成图。
查一下 LiFePO4 的结构并可视化。
```

系统第一版目标链路:

```text
1. 前端上传文件。
2. 后端保存文件，生成 file_id 和 metadata。
3. 前端发送聊天请求 { query, file_ids }。
4. workflow 把用户问题和上传文件摘要交给 LLM。
5. LLM 只调用统一工具 render_with_mcp，并只输出 intent/input_type/file_id。
6. 后端 router 根据 intent + file metadata 选择白名单 server/tool。
7. gateway 调用远程 MCP tools/call。
8. MCP 返回 render_url。
9. workflow 聚合 artifacts[]。
10. SSE final 返回 answer + viz + artifacts。
11. 前端展示现有 viz 面板，同时展示 artifact iframe 面板。
```

最终响应契约:

```json
{
  "answer": "已生成 DOS 和 XRD 可视化结果。",
  "viz": null,
  "artifacts": [
    {
      "id": "artifact_1",
      "kind": "mcp_visualization",
      "title": "DOS 可视化",
      "intent": "dos",
      "display": "iframe",
      "render_url": "http://...",
      "created_at": 1782892800,
      "expires_at": 1782893400,
      "source_file_id": "file_20260701_abcd1234"
    }
  ]
}
```

短期保留 `viz` 是为了兼容当前结构分析和 3DGS viewer；新 MCP 可视化结果走 `artifacts`。

---

## 3. 设计原则

### 3.1 LLM 只判断 intent，不直接选择远程工具

不把远程 `dos.dos_file`、`x_ray.xrd_file`、`hot2.binary_xlsx_file` 等工具裸露给 LLM。

原因:

- LLM 可能编造不存在的 tool name。
- LLM 不应处理本地路径、base64 文件内容、密钥、server 白名单。
- 后续增加 server 不应大幅改 prompt。

LLM 只看到统一工具:

```text
render_with_mcp
```

LLM 输出:

```json
{
  "intent": "dos",
  "input_type": "file",
  "file_id": "file_20260701_abcd1234"
}
```

后端路由到:

```text
dos-mcp-server / dos.dos_file
```

### 3.2 后端是安全边界

后端必须负责:

- `file_id` 是否存在。
- 文件是否位于上传目录或系统生成文件目录内。
- 文件后缀是否匹配 route。
- server/tool 是否在白名单内。
- 是否允许把该文件 base64 发送到远程 MCP。
- 远程调用审计日志。

### 3.3 前端只渲染 artifact

前端不应该理解 MCP route table。

前端只根据 artifact 的 `display` 渲染:

```text
display = iframe -> iframe + 打开新窗口 + 复制链接 + 刷新
display = image  -> img, Phase 3
display = data   -> 原生图表, Phase 3
display = file   -> 文件预览/下载, Phase 3
```

第一版只实现:

```text
display = iframe
```

### 3.4 渐进迁移，不替换现有 3DGS

当前 `viz` 和 3DGS MCP viewer 是已有主能力，不应被第一版通用 MCP 改造破坏。

第一版 UI 策略:

```text
VisualizationPanel(viz) 保留
ArtifactPanel(artifacts) 新增
```

后续再考虑把 3DGS MCP viewer 也包装成 artifact。

---

## 4. Phase 0: 数据契约和工程基础

Phase 0 是第一版闭环前的必要准备。没有这一步，上传文件和 artifacts 无法贯穿前后端。

### 4.1 后端 schema

修改 `api/schemas.py`:

```python
class ChatRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=10000)
    file_ids: list[str] = Field(default_factory=list, max_length=10)


class UploadedFileResponse(BaseModel):
    file_id: str
    filename: str
    extension: str
    mime_type: str | None = None
    size_bytes: int
    sha256: str
    created_at: float
    source: str = "user_upload"
```

`McpRenderRequest` 短期保留，用于兼容 `/api/mcp/render`。

### 4.2 WorkflowContext

修改 `core/workflow_types.py`:

```python
@dataclass
class WorkflowContext:
    question: str
    trace_id: str
    file_ids: list[str] = field(default_factory=list)
    uploaded_files: list[dict[str, Any]] = field(default_factory=list)
    artifacts: list[dict[str, Any]] = field(default_factory=list)
    ...
```

保留:

```python
viz_result: dict[str, Any] = field(default_factory=dict)
```

### 4.3 SSE final 事件

修改 `core/workflow.py` 和 `api/serialization.py`，final 事件统一包含:

```json
{
  "type": "final",
  "trace_id": "...",
  "answer": "...",
  "viz": {},
  "artifacts": [],
  "step_results": []
}
```

序列化要求:

- `viz` 继续走现有 `serialize_viz()`。
- `artifacts` 走 `_json_safe()`。
- artifact 中不要放本地真实路径。

### 4.4 前端类型和请求

修改 `frontend/src/types.ts`:

```ts
export interface UploadedFile {
  file_id: string;
  filename: string;
  extension: string;
  mime_type?: string | null;
  size_bytes: number;
  sha256?: string;
  created_at: number;
}

export interface Artifact {
  id: string;
  kind: "mcp_visualization";
  title: string;
  intent: string;
  display: "iframe";
  render_url: string;
  created_at?: number;
  expires_at?: number;
  source_file_id?: string;
  warnings?: string[];
}

export interface WorkflowEvent {
  ...
  artifacts?: Artifact[];
}
```

修改 `frontend/src/api.ts`:

```ts
streamChat(query: string, fileIds: string[], onEvent, signal)
```

发送:

```json
{
  "query": "...",
  "file_ids": ["file_..."]
}
```

### 4.5 依赖和忽略规则

修改 `requirements.txt`:

```text
python-multipart
```

修改 `.gitignore`:

```text
static/uploads/
static/artifacts/
```

---

## 5. Phase 1: 第一版最小闭环

### 5.1 配置

修改 `config/settings.py`:

```python
MCP_TOOL_GATEWAY_ENABLED = ...
MCP_CONFIG_DIR = Path(os.getenv("MCP_CONFIG_DIR", BASE_DIR / "docs" / "server_json"))
MCP_UPLOAD_DIR = Path(os.getenv("MCP_UPLOAD_DIR", STATIC_DIR / "uploads"))
MCP_MAX_UPLOAD_MB = int(os.getenv("MCP_MAX_UPLOAD_MB", "100"))
MCP_MAX_FILES_PER_REQUEST = int(os.getenv("MCP_MAX_FILES_PER_REQUEST", "10"))
MCP_ALLOWED_UPLOAD_EXTENSIONS = {...}
```

保留旧配置:

```python
MCP_ENABLED
MCP_SERVER_URL
MCP_API_KEY
```

用途:

- `/api/mcp/render` 兼容旧路径。
- 回滚时可继续使用旧单 server 路径。

### 5.2 Upload store

新增 `core/upload_store.py`。

职责:

- 生成不可预测 `file_id`。
- 保存原始文件。
- 保存 `metadata.json`。
- 计算 `sha256`。
- 校验大小、后缀、路径。
- 根据 `file_id` 安全解析文件。
- 支持用户上传文件和系统生成文件。

建议目录:

```text
static/uploads/
  file_20260701_abcd1234/
    original.txt
    metadata.json
```

metadata:

```json
{
  "file_id": "file_20260701_abcd1234",
  "source": "user_upload",
  "original_filename": "dos.txt",
  "stored_filename": "original.txt",
  "extension": ".txt",
  "mime_type": "text/plain",
  "size_bytes": 12345,
  "sha256": "...",
  "created_at": 1782892800
}
```

安全要求:

- `file_id` 只允许匹配后端生成格式。
- 不接受任意本地路径。
- `resolve_file(file_id)` 后必须确认路径在 `MCP_UPLOAD_DIR` 内。
- 后续如果支持登录，需要把 `owner_id` 加进 metadata。

### 5.3 文件上传 API

可在 `api/main.py` 直接加，也可以新增 `api/files.py` 后 include router。

第一版建议新增 `api/files.py`:

```text
POST /api/files/upload
Content-Type: multipart/form-data
```

返回:

```json
{
  "file_id": "file_20260701_abcd1234",
  "filename": "dos.txt",
  "extension": ".txt",
  "mime_type": "text/plain",
  "size_bytes": 12345,
  "sha256": "...",
  "created_at": 1782892800
}
```

第一版允许直接上传的可视化数据文件:

```text
.cif, .xyz, .poscar, .cell, .pdb
.dat, .txt
.xls, .xlsx
```

第二期再打开:

```text
.zip, .vtp, .stl, .glb, .dump, .cfg, .data, .lmp
.pdf, .doc, .docx, .jpg, .jpeg, .png
```

### 5.4 MCP registry

新增 `core/mcp_registry.py`。

职责:

- 读取 `MCP_CONFIG_DIR` 下所有 `.json`。
- 支持当前格式:

```json
{
  "mcpServers": {
    "dos-mcp-server": {
      "url": "http://219.232.220.140/view_mcp/dos/mcp",
      "headers": {
        "visualization-api-key": "..."
      }
    }
  }
}
```

- 合并成内部 registry:

```python
{
    "dos-mcp-server": {
        "url": "...",
        "headers": {"visualization-api-key": "..."},
    }
}
```

- 校验:
  - server name 非空。
  - url 是绝对 http/https。
  - headers 是 dict[str, str]。
  - 重复 server name 报错。

注意:

- registry 只提供配置，不代表用户可任意调用。
- 用户可调用能力由 `core/mcp_router.py` 的白名单 route table 决定。

### 5.5 MCP gateway

新增 `core/mcp_gateway.py`。

职责:

- `call_tool(server_name, tool_name, arguments) -> dict`
- 从 registry 取 server url 和 headers。
- 发送 JSON-RPC:

```json
{
  "jsonrpc": "2.0",
  "id": "...",
  "method": "tools/call",
  "params": {
    "name": "dos.dos_file",
    "arguments": {}
  }
}
```

- 支持 plain JSON 和 SSE JSON 响应。
- 支持 result 形态:
  - `result.render_url`
  - `result.structuredContent.render_url`
  - `result.content[].text` 中的 JSON 字符串。
- 支持 tool error:
  - `result.isError == true`
  - RPC `error`
- 第一版可以先走 stateless JSON-RPC。
- 后续兼容 sessionful MCP 时，复用 `core/3dgs_mcp_client.py` 的 initialize/session 逻辑。

建议错误类型:

```python
class MCPGatewayError(RuntimeError): ...
class MCPRegistryError(MCPGatewayError): ...
class MCPToolError(MCPGatewayError): ...
class MCPRenderUrlMissingError(MCPGatewayError): ...
```

### 5.6 MCP router

新增 `core/mcp_router.py`。

第一版 route table:

| intent | server | file tool | url tool | 文件类型 |
| --- | --- | --- | --- | --- |
| `structure` | `fz-mcp-server` | `fz.mol_file` | `fz.mol_url` | `.cif`, `.xyz`, `.poscar`, `.cell`, `.pdb` |
| `dos` | `dos-mcp-server` | `dos.dos_file` | `dos.dos_url` | `.dat`, `.txt` |
| `xrd` | `x-ray-mcp-server` | `x_ray.xrd_file` | `x_ray.xrd_url` | `.dat`, `.txt` |
| `binary_phase` | `hot2-mcp-server` | `hot2.binary_xlsx_file` | `hot2.binary_xlsx_url` | `.xls`, `.xlsx` |
| `ternary_phase` | `hot3-mcp-server` | `hot3.ternary_xlsx_file` | `hot3.ternary_xlsx_url` | `.xls`, `.xlsx` |

第一版只启用 `input_type=file`。

`url_tool` 保留在 route table 中，但 URL 调用放到 Phase 2。

解析规则:

- intent 必须在 route table。
- `input_type=file` 时必须有 `file_id`。
- 文件后缀必须在 route.extensions。
- `.txt` / `.dat` / `.xlsx` 只做后缀校验，不做唯一 intent 判断。
- intent 不明确时 workflow 应要求用户澄清，不应让 router 猜。

### 5.7 render_with_mcp 工具

修改 `core/tools.py`，新增 OpenAI tool spec:

```json
{
  "type": "function",
  "function": {
    "name": "render_with_mcp",
    "description": "Render an uploaded or system-generated materials file with a whitelisted MCP visualization route.",
    "parameters": {
      "type": "object",
      "properties": {
        "intent": {
          "type": "string",
          "enum": ["structure", "dos", "xrd", "binary_phase", "ternary_phase"]
        },
        "input_type": {
          "type": "string",
          "enum": ["file"]
        },
        "file_id": {
          "type": "string",
          "description": "The uploaded or system-generated file_id shown in the conversation context."
        }
      },
      "required": ["intent", "input_type", "file_id"],
      "additionalProperties": false
    }
  }
}
```

`execute_openai_tool("render_with_mcp", args)` 流程:

```text
1. upload_store.resolve_file(file_id)
2. mcp_router.resolve_route(intent, input_type, file metadata)
3. 读取文件 bytes -> base64
4. gateway.call_tool(server, file_tool, arguments)
5. 提取 render_url
6. 生成 artifact dict
7. 返回 artifact
```

MCP file tool arguments 第一版统一:

```json
{
  "filename": "dos.txt",
  "content_base64": "..."
}
```

如果某个 server 实际参数不同，优先在 route table 加 `argument_style` 或 `argument_builder`，不要让 LLM 决定参数形态。

### 5.8 Workflow 改造

修改 `core/workflow.py`。

入口:

```python
def run_stream(self, question: str, file_ids: list[str] | None = None)
```

`api/main.py`:

```python
orchestrator.run_stream(request.query, file_ids=request.file_ids)
```

workflow 初始化时:

```text
1. 根据 file_ids 加载 metadata。
2. 写入 ctx.uploaded_files。
3. 把文件摘要注入 user/system context。
```

文件摘要示例:

```text
用户已上传文件:
- file_id: file_20260701_abcd1234
  filename: dos.txt
  extension: .txt
  size_bytes: 12345
- file_id: file_20260701_efgh5678
  filename: xrd.txt
  extension: .txt
  size_bytes: 18000
```

新增 prompt 约束:

```text
当用户要求可视化上传文件、绘制 DOS/XRD/相图/结构时，调用 render_with_mcp。
不要编造 MCP server 名称或工具名称。
只能使用上下文中列出的 file_id。
如果请求需要多个可视化结果，可以多次调用 render_with_mcp。
如果多个 .txt/.dat 文件用途不明确，先要求用户澄清。
PDF/DOC/JPG/PNG 第一版不直接调用 MCP 可视化工具。
```

工具调用结果处理:

- `render_with_mcp` 成功时，把 artifact append 到 `ctx.artifacts`。
- `step_end` 中记录 intent、file_id、artifact id。
- final 返回 `ctx.artifacts`。

### 5.9 系统生成 CIF 的处理

当前 `get_mp_structure` 会生成 CIF，并形成 `viz_result`。

为了支持:

```text
查一下 LiFePO4 的结构并可视化。
```

第一版有两种可选实现:

#### 推荐实现

`get_mp_structure_raw()` 生成 CIF 后，调用 upload store 注册系统文件:

```json
{
  "file_id": "file_20260701_system_abcd1234",
  "source": "system_generated",
  "original_filename": "mp-1661648_LiFePO4.cif",
  "extension": ".cif"
}
```

工具结果返回 `generated_file_id`，下一轮 LLM 可调用:

```json
{
  "intent": "structure",
  "input_type": "file",
  "file_id": "file_20260701_system_abcd1234"
}
```

#### 简化实现

如果短期不想改 `get_mp_structure_raw()`，workflow 在看到 `ctx.viz_result.cif_path` 后内部创建 system file_id，并把它加入 context。

不要让 LLM 直接拿 `cif_path` 调 MCP。

### 5.10 前端上传和 artifact 展示

新增 API:

```ts
uploadFile(file: File): Promise<UploadedFile>
```

修改 `ChatPanel`:

- 增加文件选择按钮。
- 上传成功后展示附件 chip。
- 支持移除附件。
- 发送消息时把附件 file_ids 传给 `onSubmit(query, fileIds)`。

修改 `App.tsx`:

```ts
const [attachments, setAttachments] = useState<UploadedFile[]>([]);
const [artifacts, setArtifacts] = useState<Artifact[]>([]);
```

final 事件:

```ts
setViz(event.viz ?? null);
setArtifacts(event.artifacts ?? []);
```

新增组件:

```text
frontend/src/components/ArtifactPanel.tsx
frontend/src/components/ArtifactGrid.tsx
frontend/src/components/McpIframeArtifact.tsx
```

`McpIframeArtifact` 功能:

- iframe 展示 `render_url`。
- 打开新窗口。
- 复制链接。
- 刷新 iframe。
- 加载超时提示“可能禁止嵌入，请在新窗口打开”。

复用 `McpViewer` 的思路:

- loading/error 状态。
- TTL/过期提示。
- iframe fallback。

第一版不要求探测 `X-Frame-Options` 和 CSP，只做前端超时降级。

---

## 6. Phase 1.5: 兼容和整合

Phase 1.5 在最小闭环跑通后做，避免第一版改动过大。

### 6.1 兼容 `/api/mcp/render`

当前旧接口:

```text
POST /api/mcp/render { cif_path }
```

短期保留。

可选改造:

- 内部注册 CIF 为 system file。
- 走 `mcp_router` 的 `structure` route。
- 返回旧 `McpRenderResponse` 形态，避免破坏 `McpViewer`。

### 6.2 3DGS artifact 化

当前 3DGS 仍走:

```text
POST /api/3dgs/render
```

第一版不改。

后续可以把 3DGS MCP viewer 包装成 artifact:

```json
{
  "id": "artifact_3dgs_...",
  "kind": "mcp_visualization",
  "source": "3dgs:mcp",
  "display": "iframe",
  "title": "3DGS 结构视图",
  "render_url": "http://127.0.0.1:8090/viewer/sessions/..."
}
```

### 6.3 管理/诊断接口

可加:

```text
GET /api/mcp/servers
GET /api/mcp/routes
```

用途:

- 查看 registry 是否加载成功。
- 查看白名单 route table。
- 前端或调试页面展示 MCP gateway 状态。

不建议第一版调用真实远程 `tools/list` 作为生产路由依据。

---

## 7. Phase 2: 扩展输入和更多工具

Phase 2 在 Phase 1 稳定后做。

### 7.1 URL 输入

开启:

```json
{
  "input_type": "url",
  "http_url": "https://..."
}
```

必须先实现 SSRF 防护:

- 只允许 http/https。
- 禁止 localhost。
- 禁止 127.0.0.0/8。
- 禁止 10.0.0.0/8、172.16.0.0/12、192.168.0.0/16。
- 禁止 link-local、metadata IP。
- 可选 DNS resolve 后再次校验。

### 7.2 文档和图片上下文

支持:

```text
.pdf, .doc, .docx, .jpg, .jpeg, .png
```

第一目标:

- 提取文本。
- 提取 URL。
- 帮 LLM 判断用户想处理哪个文件。

不做:

- 从论文图片自动还原 DOS/XRD 原始曲线数据。

### 7.3 第二批 MCP routes

| intent | server | file tool | url tool | 文件类型 |
| --- | --- | --- | --- | --- |
| `band` | `nb-mcp-server` | `nb.band_zip_file` | `nb.band_zip_url` | `.zip` |
| `vtp` | `yxy-mcp-server` | `yxy.vtp_file` | `yxy.vtp_url` | `.vtp` |
| `model` | `hj-ol-mcp-server` | `hj_ol.model_file` | `hj_ol.model_url` | `.stl`, `.glb` |
| `molecular_dynamics` | `fzdl-mcp-server` | `fzdl.model_file` | `fzdl.model_url` | `.dump`, `.cfg`, `.data`, `.dat`, `.lmp`, `.xyz` |
| `phase_curve` | `xt-mcp-server` | `xt.phase_curve_file` | `xt.phase_curve_url` | `.dat`, `.txt` |
| `liquidus` | `yxty3-mcp-server` | `yxty3.liquidus_xlsx_file` | `yxty3.liquidus_xlsx_url` | `.xls`, `.xlsx` |
| `isothermal` | `dw3-mcp-server` | `dw3.isothermal_xlsx_file` | `dw3.isothermal_xlsx_url` | `.xls`, `.xlsx` |
| `vertical_section` | `cz3-mcp-server` | `cz3.vertical_xlsx_file` | `cz3.vertical_xlsx_url` | `.xls`, `.xlsx` |

`dw3` / `yxty3` 的 `_dual`、`_mass` 变体后续增加参数:

```text
composition_basis = atom | mass
mode = single | dual
```

由后端 router 选择具体 tool。

---

## 8. Phase 3: 产品化 API / SDK

Phase 3 与第一版内部 UI 闭环解耦，不阻塞 Phase 1。

目标:

```text
Visualization Agent API / SDK
```

建议异步任务 API:

```http
POST /v1/render-jobs
GET /v1/render-jobs/{job_id}
GET /v1/artifacts/{artifact_id}
GET /v1/artifacts/{artifact_id}/view
GET /v1/artifacts/{artifact_id}/preview.png
```

能力:

- API key 鉴权。
- 调用方隔离。
- job ownership。
- artifact ownership。
- rate limit。
- file count limit。
- artifact TTL 清理。
- 可选截图 `image_url`。

静态截图服务:

```text
MCP render_url
  -> Playwright/Chromium
  -> 等待渲染稳定
  -> 截图 PNG
  -> static/artifacts
  -> image_url
```

截图失败不应导致整个 job 失败。如果已有 `render_url`，返回 warning。

---

## 9. 实施顺序

### 9.1 Phase 0

1. 修改 `api/schemas.py`: `ChatRequest.file_ids`、上传响应 schema。
2. 修改 `core/workflow_types.py`: `file_ids`、`uploaded_files`、`artifacts`。
3. 修改 `api/serialization.py`: final 支持 `artifacts`。
4. 修改 `frontend/src/types.ts`: `UploadedFile`、`Artifact`、`WorkflowEvent.artifacts`。
5. 修改 `frontend/src/api.ts`: `streamChat(query, fileIds, ...)`。
6. 修改 `requirements.txt`: 增加 `python-multipart`。
7. 修改 `.gitignore`: 忽略 `static/uploads/`、`static/artifacts/`。

### 9.2 Phase 1 后端

1. 修改 `config/settings.py`: 新增 MCP gateway/upload 配置。
2. 新增 `core/upload_store.py`。
3. 新增 `api/files.py` 或在 `api/main.py` 增加 `/api/files/upload`。
4. 新增 `core/mcp_registry.py`。
5. 新增 `core/mcp_gateway.py`。
6. 新增 `core/mcp_router.py`。
7. 修改 `core/tools.py`: 增加 `render_with_mcp`。
8. 修改 `core/workflow.py`: 注入文件上下文、处理 `render_with_mcp` artifact。
9. 处理系统生成 CIF 注册为 system file。

### 9.3 Phase 1 前端

1. 修改 `ChatPanel`: 上传控件、附件 chip。
2. 修改 `App`: 保存 attachments/artifacts，传递 file_ids。
3. 新增 `ArtifactPanel` / `ArtifactGrid` / `McpIframeArtifact`。
4. 在主布局中让 `VisualizationPanel(viz)` 和 `ArtifactPanel(artifacts)` 并存。
5. 增加 iframe 加载失败降级。

### 9.4 Phase 1 验收

成功场景:

```text
上传 CIF，输入“把这个结构可视化”
  -> 生成 structure artifact，iframe 展示。

上传 dos.txt，输入“画 DOS”
  -> 生成 dos artifact，iframe 展示。

上传 xrd.txt，输入“画 XRD”
  -> 生成 xrd artifact，iframe 展示。

上传两个 txt，输入“第一个画 DOS，第二个画 XRD”
  -> 同时生成两个 artifacts。

上传 xlsx，输入“这是二元相图，帮我画出来”
  -> 生成 binary_phase artifact。

输入“查一下 LiFePO4 的结构并可视化”
  -> get_mp_structure 生成 CIF
  -> 系统注册 generated_file_id
  -> 生成 structure artifact 或保留 viz + 生成 artifact。
```

错误场景:

```text
上传 pdf，输入“直接画 DOS”
  -> 不调用 dos.dos_file，提示 PDF 第一版不是直接可视化数据文件。

上传 txt，用户没有说明 DOS 还是 XRD
  -> 要求用户明确用途，或在文件名明确时谨慎判断。

MCP 返回无 render_url
  -> step_end 标记失败，final answer 说明失败原因，前端不显示空白 artifact。

file_id 不存在或路径逃逸
  -> 后端 400/404，不调用 MCP。
```

---

## 10. 测试计划

所有 Python 命令按项目约定使用 Conda 环境:

```powershell
conda run -n agno-assist python ...
conda run -n agno-assist pytest ...
conda run -n agno-assist python -m pip ...
```

### 10.1 后端单元测试

新增:

```text
tests/test_upload_store.py
tests/test_mcp_registry.py
tests/test_mcp_router.py
tests/test_mcp_gateway.py
tests/test_workflow_mcp_artifacts.py
```

覆盖:

- 上传文件 metadata 写入。
- 超大文件拒绝。
- 不允许后缀拒绝。
- file_id 格式校验。
- 路径逃逸防护。
- `docs/server_json` 加载。
- 重复 server name 报错。
- intent -> server/tool 路由。
- 后缀不匹配时报错。
- plain JSON / SSE JSON 解析。
- `structuredContent.render_url` 提取。
- `content[].text` render_url 提取。
- tool error 变成清晰异常。
- workflow 多 artifact 聚合。

### 10.2 后端集成测试

使用 mock MCP server，不访问真实远程服务。

验证:

```text
POST /api/files/upload
POST /api/chat
POST /api/chat/stream
POST /api/mcp/render 兼容路径
```

### 10.3 前端验证

至少运行:

```powershell
npm --prefix frontend run build
```

如涉及布局或 iframe:

```powershell
npm --prefix frontend run visual:smoke
```

覆盖:

- 上传成功展示附件 chip。
- 删除附件。
- 发送请求携带 file_ids。
- final 事件渲染多个 artifacts。
- iframe fallback 展示“打开新窗口”。
- 移动端布局不重叠。

---

## 11. 风险和决策点

### 11.1 远程 MCP 参数是否统一

计划默认所有 file tool 接收:

```json
{
  "filename": "...",
  "content_base64": "..."
}
```

需要用真实 MCP server 或 mock server 验证。

如果存在差异，在 route table 中加入参数构造策略，不交给 LLM。

### 11.2 iframe 是否允许嵌入

真实 `render_url` 可能被:

- `X-Frame-Options`
- CSP `frame-ancestors`

限制。

第一版前端降级为“打开新窗口”。Phase 2 再做兼容性探测。

### 11.3 上传文件外传提示

`*_file` 调用会把用户上传内容 base64 发送到远程 MCP server。

第一版建议 UI 增加明确提示:

```text
可视化时文件会发送到远程 MCP 服务进行渲染。
```

### 11.4 密钥管理

`docs/server_json` 当前含测试 key 形态字段。

后续要明确:

- 示例配置可提交。
- 真实 key 只能在 `.env` 或本地未跟踪配置中。
- 如需要覆盖 headers，可支持环境变量注入。

### 11.5 用户隔离

当前项目没有登录态。

第一版 metadata 不绑定用户也可跑通本地 demo。

若要部署给多用户，必须补:

- owner/session 绑定。
- 上传文件访问隔离。
- artifact 访问隔离。
- 清理任务。

---

## 12. 第一版最小闭环总结

第一版只做这条链路:

```text
上传文件
-> file_id
-> chat { query, file_ids }
-> LLM render_with_mcp(intent, file_id)
-> 后端白名单 route
-> MCP gateway tools/call
-> render_url
-> artifacts[]
-> 前端 iframe 展示
```

保留现有能力:

```text
Materials Project 查询
CIF 解析
viz
3DGS MCP viewer
旧 /api/mcp/render
```

不在第一版混入:

```text
PDF/DOC/JPG 理解
URL SSRF 完整链路
截图 image_url
第三方 API/SDK
```

这样改动边界清楚，失败时也容易定位是上传、路由、gateway、workflow 还是前端展示的问题。
