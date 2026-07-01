# MCP 工具扩展两期开发方案

> 适用版本: 2026-07  
> 目标: 将远程 MCP 可视化服务接入为系统级工具扩展，使用户通过自然语言和上传文件触发 LLM 意图解析、后端受控路由、MCP 工具调用，并在前端同时展示多个可视化结果。

---

## 一、目标效果

用户不需要理解 MCP server、tool name 或文件类型规则。用户只需要上传文件并用自然语言描述目标:

```text
把这个 DOS 数据画出来。
把这两个 txt 分别按 DOS 和 XRD 可视化。
这个 Excel 是二元相图数据，帮我生成图。
查一下 LiFePO4 的结构并可视化。
```

系统完成以下流程:

```text
1. 前端上传文件，后端保存并生成 file_id。
2. 用户问题和 file_id 一起进入对话工作流。
3. LLM 识别用户意图，例如 structure、dos、xrd、binary_phase。
4. 后端根据 intent、文件后缀、MCP 白名单选择具体 server/tool。
5. 后端调用对应 MCP tools/call。
6. MCP 返回 render_url。
7. 前端把每个 render_url 作为 iframe artifact 同时展示。
```

最终前端展示应由单一 `viz` 升级为多个 `artifacts`:

```json
{
  "answer": "已生成 DOS 和 XRD 可视化结果。",
  "artifacts": [
    {
      "id": "artifact_1",
      "kind": "mcp_visualization",
      "title": "DOS 可视化",
      "intent": "dos",
      "server": "dos-mcp-server",
      "tool": "dos.dos_file",
      "display": "iframe",
      "render_url": "http://..."
    },
    {
      "id": "artifact_2",
      "kind": "mcp_visualization",
      "title": "XRD 可视化",
      "intent": "xrd",
      "server": "x-ray-mcp-server",
      "tool": "x_ray.xrd_file",
      "display": "iframe",
      "render_url": "http://..."
    }
  ]
}
```

---

## 二、设计原则

### 2.1 LLM 只判断意图，不直接选择任意远程工具

不建议把所有 MCP 工具裸露给 LLM，让 LLM 自己生成 `dos.dos_file`、`x_ray.xrd_file` 这类工具名。原因:

- LLM 可能编造不存在的工具名。
- LLM 不适合直接处理文件路径安全、MCP 鉴权、工具白名单。
- 后续增加 MCP server 时不希望改大量 prompt。

推荐只暴露一个统一后端工具:

```text
render_with_mcp
```

LLM 负责输出:

```json
{
  "intent": "dos",
  "input_type": "file",
  "file_id": "file_abc"
}
```

后端负责将其路由到:

```text
dos-mcp-server / dos.dos_file
```

### 2.2 后端是 MCP 网关和安全边界

后端必须控制:

- 文件是否来自已上传文件库。
- 文件后缀是否匹配工具要求。
- MCP server 是否在白名单内。
- MCP tool 是否在白名单内。
- 是否允许把文件内容 base64 上传到远程 MCP。

### 2.3 前端只关心 artifact，不关心 MCP 细节

前端不应该知道 `dos.dos_file`、`hot2.binary_xlsx_file` 的业务细节。前端只根据 artifact 的 `display` 字段渲染:

```text
display = iframe -> iframe 展示 render_url
display = image  -> img 展示 image_url
display = data   -> 原生图表组件展示结构化数据
display = file   -> 文件预览/下载
```

第一期只实现:

```text
display = iframe
```

---

## 三、总体架构

### 3.1 当前架构限制

现有通用 MCP 链路接近如下:

```text
POST /api/mcp/render
  -> api.main.mcp_render()
  -> core.mcp_client.process_file()
  -> MCP_SERVER_URL
  -> tools/call: fz.process_file
  -> render_url
```

当前问题:

- 只支持一个 `MCP_SERVER_URL`。
- 工具名写死为旧的 `fz.process_file` / `fz.process_http`。
- 请求模型只面向 CIF，不适合 DOS、XRD、相图、能带、VTP 等工具。
- 最终结果只有单个 `viz`，不适合同时展示多个 MCP 输出。

### 3.2 目标架构

```text
前端上传文件
  -> POST /api/files/upload
  -> 后端保存文件并返回 file_id

用户自然语言提问
  -> POST /api/chat/stream { query, file_ids }
  -> WorkflowOrchestrator
  -> LLM function calling: render_with_mcp
  -> core.mcp_router.resolve_route()
  -> core.mcp_gateway.call_tool()
  -> 远程 MCP server
  -> render_url
  -> artifacts[]
  -> 前端 iframe 面板同时展示
```

### 3.3 模块拆分

建议新增或改造以下模块:

```text
core/mcp_registry.py      读取 server_json 和 MCP server 配置
core/mcp_gateway.py       通用 JSON-RPC MCP client
core/mcp_router.py        intent + 文件类型 -> server/tool 路由
core/upload_store.py      上传文件元数据、路径解析和安全校验
api/files.py              文件上传 API
api/schemas.py            扩展 chat/mcp 请求模型
core/tools.py             增加 render_with_mcp 工具
core/workflow.py          支持 artifacts[] 聚合输出
frontend                  上传控件 + artifact iframe 面板
```

---

## 四、MCP 配置与路由

### 4.1 配置来源

远程 MCP 配置当前位于:

```text
C:/Users/wyfz/OneDrive/Desktop/server_json/
```

建议不要在代码里硬编码这个路径，而是在 `.env` 中增加:

```env
MCP_CONFIG_DIR=C:/Users/wyfz/OneDrive/Desktop/server_json
MCP_TOOL_GATEWAY_ENABLED=true
MCP_UPLOAD_DIR=static/uploads
MCP_MAX_UPLOAD_MB=100
```

`core/mcp_registry.py` 负责读取目录内的 JSON:

```json
{
  "mcpServers": {
    "dos-mcp-server": {
      "url": "http://219.232.220.140/view_mcp/dos/mcp",
      "headers": {
        "visualization-api-key": "THIS_IS_TEST_KEY_12321"
      }
    }
  }
}
```

内部统一成:

```python
{
    "dos-mcp-server": {
        "url": "...",
        "headers": {"visualization-api-key": "..."},
    }
}
```

### 4.2 第一版路由表

先采用显式白名单路由，不依赖远程 `tools/list` 动态决定用户可调用能力。

```python
MCP_ROUTE_TABLE = {
    "structure": {
        "title": "结构可视化",
        "server": "fz-mcp-server",
        "file_tool": "fz.mol_file",
        "url_tool": "fz.mol_url",
        "extensions": [".cif", ".xyz", ".poscar", ".cell", ".pdb"],
    },
    "dos": {
        "title": "DOS 可视化",
        "server": "dos-mcp-server",
        "file_tool": "dos.dos_file",
        "url_tool": "dos.dos_url",
        "extensions": [".dat", ".txt"],
    },
    "xrd": {
        "title": "XRD 可视化",
        "server": "x-ray-mcp-server",
        "file_tool": "x_ray.xrd_file",
        "url_tool": "x_ray.xrd_url",
        "extensions": [".dat", ".txt"],
    },
    "binary_phase": {
        "title": "二元相图可视化",
        "server": "hot2-mcp-server",
        "file_tool": "hot2.binary_xlsx_file",
        "url_tool": "hot2.binary_xlsx_url",
        "extensions": [".xls", ".xlsx"],
    },
    "ternary_phase": {
        "title": "三元相图可视化",
        "server": "hot3-mcp-server",
        "file_tool": "hot3.ternary_xlsx_file",
        "url_tool": "hot3.ternary_xlsx_url",
        "extensions": [".xls", ".xlsx"],
    },
}
```

### 4.3 第二期扩展路由

第二期加入更多工具:

```python
{
    "band": "nb.band_zip_file / nb.band_zip_url",
    "vtp": "yxy.vtp_file / yxy.vtp_url",
    "model": "hj_ol.model_file / hj_ol.model_url",
    "molecular_dynamics": "fzdl.model_file / fzdl.model_url",
    "phase_curve": "xt.phase_curve_file / xt.phase_curve_url",
    "liquidus": "yxty3.liquidus_xlsx_file / yxty3.liquidus_xlsx_url",
    "isothermal": "dw3.isothermal_xlsx_file / dw3.isothermal_xlsx_url",
    "vertical_section": "cz3.vertical_xlsx_file / cz3.vertical_xlsx_url",
}
```

对于 `.txt`、`.dat`、`.xlsx` 这种多义后缀，必须依赖 intent。文件后缀只做校验，不做最终唯一判断。

---

## 五、上传文件设计

### 5.1 支持文件类型

用户要求支持:

```text
txt, doc, pdf, jpg 等文件
```

第一期按用途分成两类:

#### 可直接进入 MCP 可视化的材料数据文件

```text
.cif, .xyz, .poscar, .cell, .pdb
.dat, .txt
.xls, .xlsx
.zip
.vtp
.stl, .glb
```

#### 作为上下文解析的文档/图片文件

```text
.pdf, .doc, .docx, .jpg, .jpeg, .png
```

文档/图片通常不能直接调用现有 MCP 可视化工具。它们第一版用途是:

- 提取文本给 LLM 作为上下文。
- 从文档中识别数据文件 URL。
- 让 LLM 判断用户真正想处理哪个上传文件。

如果 PDF 或 DOC 内包含数据表，第二期再考虑表格抽取并转换为 MCP 可接受的数据文件。

### 5.2 上传 API

新增:

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
  "created_at": 1782892800
}
```

聊天接口扩展:

```json
{
  "query": "把这个 DOS 数据画出来",
  "file_ids": ["file_20260701_abcd1234"]
}
```

### 5.3 文件存储

建议目录:

```text
static/uploads/
  file_20260701_abcd1234/
    original.txt
    metadata.json
```

`metadata.json` 示例:

```json
{
  "file_id": "file_20260701_abcd1234",
  "original_filename": "dos.txt",
  "stored_filename": "original.txt",
  "extension": ".txt",
  "mime_type": "text/plain",
  "size_bytes": 12345,
  "sha256": "...",
  "created_at": 1782892800
}
```

安全约束:

- 所有 MCP 文件调用只能使用 `file_id`，不能让 LLM 传任意本地路径。
- 后端解析 file_id 后必须确认路径位于 `static/uploads` 内。
- 上传大小和后缀必须校验。
- 临时文件和用户上传文件默认不提交 git。

---

## 六、LLM 工具设计

### 6.1 新增统一工具 render_with_mcp

在 `core/tools.py` 中新增 OpenAI function spec:

```json
{
  "name": "render_with_mcp",
  "description": "Render an uploaded material/scientific file or URL with a whitelisted MCP visualization tool.",
  "parameters": {
    "type": "object",
    "properties": {
      "intent": {
        "type": "string",
        "enum": [
          "structure",
          "dos",
          "xrd",
          "binary_phase",
          "ternary_phase",
          "band",
          "vtp",
          "model",
          "liquidus",
          "isothermal",
          "vertical_section"
        ]
      },
      "input_type": {
        "type": "string",
        "enum": ["file", "url"]
      },
      "file_id": {
        "type": ["string", "null"]
      },
      "http_url": {
        "type": ["string", "null"]
      }
    },
    "required": ["intent", "input_type"],
    "additionalProperties": false
  }
}
```

### 6.2 Prompt 约束

系统 prompt 需要增加:

```text
当用户要求可视化上传文件、绘制 DOS/XRD/相图/能带/结构/模型时，调用 render_with_mcp。
不要自己编造 MCP server 名称或工具名称。
如果一个请求需要多个可视化结果，可以多次调用 render_with_mcp。
如果文件类型和意图不匹配，先说明无法确定，不要强行调用。
PDF/DOC/JPG 默认作为上下文文件，除非明确提取到可用数据或 URL，否则不要直接调用 MCP 可视化工具。
```

### 6.3 多工具结果聚合

`WorkflowContext` 建议新增:

```python
artifacts: list[dict[str, Any]]
```

`render_with_mcp` 每成功一次，追加一个 artifact:

```python
{
    "id": "...",
    "kind": "mcp_visualization",
    "title": route.title,
    "intent": intent,
    "server": route.server,
    "tool": selected_tool,
    "display": "iframe",
    "render_url": render_url,
    "source": f"mcp:{intent}",
    "created_at": now,
    "expires_at": now + ttl_sec,
}
```

最终 SSE `final` 事件同时返回:

```json
{
  "answer": "...",
  "viz": {},
  "artifacts": []
}
```

保留 `viz` 是为了兼容现有前端；新前端优先读取 `artifacts`。

---

## 七、前端展示设计

### 7.1 上传交互

前端输入区增加附件上传:

```text
[上传文件]  用户问题输入框  [发送]
```

上传成功后在输入框上方或下方显示附件 chip:

```text
dos.txt        12 KB    x
xrd.txt        18 KB    x
report.pdf    230 KB    x
```

发送聊天时带上 `file_ids`。

### 7.2 多 artifact 展示

新增组件:

```text
ArtifactPanel
ArtifactGrid
McpIframeArtifact
```

展示样式:

```text
助手回答

可视化结果
------------------------------------------------
| DOS 可视化                                   |
| 来源: dos-mcp-server / dos.dos_file          |
| [打开新窗口] [复制链接] [刷新]               |
| iframe(render_url)                           |
------------------------------------------------

------------------------------------------------
| XRD 可视化                                   |
| 来源: x-ray-mcp-server / x_ray.xrd_file      |
| [打开新窗口] [复制链接] [刷新]               |
| iframe(render_url)                           |
------------------------------------------------
```

### 7.3 iframe 兼容策略

第一版默认 iframe。由于用户还不确定远程 `render_url` 是否允许 iframe 嵌入，前端要做降级:

```text
1. 默认加载 iframe。
2. iframe 超时或空白时，显示“可能禁止嵌入，请在新窗口打开”。
3. 始终提供“打开新窗口”按钮。
```

需要后端或前端验证:

- `render_url` 是否可由浏览器直接访问。
- 是否存在 `X-Frame-Options: DENY/SAMEORIGIN`。
- 是否存在 CSP `frame-ancestors` 限制。

如果远程页面禁止 iframe，第二期考虑:

- 只提供新窗口打开。
- 或联系 MCP 服务端放开 frame-ancestors。
- 或由本系统提供代理页面，但代理不能保证绕过所有前端资源/CSP 限制。

---

## 八、第一期开发范围

### 8.1 目标

建立最小可用闭环:

```text
上传文件 -> 自然语言 -> LLM intent -> MCP 路由 -> 远程 tools/call -> artifacts[] -> 前端 iframe 同时展示
```

### 8.2 支持工具

第一期只支持 5 类高价值工具:

| intent | server | file tool | url tool | 文件类型 |
| --- | --- | --- | --- | --- |
| `structure` | `fz-mcp-server` | `fz.mol_file` | `fz.mol_url` | `.cif`, `.xyz`, `.poscar`, `.cell`, `.pdb` |
| `dos` | `dos-mcp-server` | `dos.dos_file` | `dos.dos_url` | `.dat`, `.txt` |
| `xrd` | `x-ray-mcp-server` | `x_ray.xrd_file` | `x_ray.xrd_url` | `.dat`, `.txt` |
| `binary_phase` | `hot2-mcp-server` | `hot2.binary_xlsx_file` | `hot2.binary_xlsx_url` | `.xls`, `.xlsx` |
| `ternary_phase` | `hot3-mcp-server` | `hot3.ternary_xlsx_file` | `hot3.ternary_xlsx_url` | `.xls`, `.xlsx` |

### 8.3 后端任务

1. 配置:
   - 增加 `MCP_CONFIG_DIR`、`MCP_TOOL_GATEWAY_ENABLED`、`MCP_UPLOAD_DIR`、`MCP_MAX_UPLOAD_MB`。

2. MCP registry:
   - 读取 `server_json` 目录。
   - 校验每个 server 的 `url` 和 `headers`。
   - 对外提供 `get_server(server_name)`。

3. MCP gateway:
   - 支持 `call_tool(server_name, tool_name, arguments)`。
   - 支持 plain JSON 和 SSE JSON 响应解析。
   - 复用现有 `_extract_render_url` 能力。

4. Upload store:
   - 新增上传目录。
   - 保存文件和 metadata。
   - 根据 file_id 安全解析路径。

5. Router:
   - 根据 intent 和 input_type 选择 route。
   - 对文件后缀做校验。
   - 对 URL 工具做白名单校验。

6. LLM tool:
   - 新增 `render_with_mcp`。
   - 支持同一用户请求多次调用。

7. Workflow:
   - `WorkflowContext` 增加 `artifacts`。
   - SSE 中 `step_end` 标记 MCP 工具调用结果。
   - final 事件返回 `artifacts`。

8. API:
   - 新增 `POST /api/files/upload`。
   - 扩展 `ChatRequest` 支持 `file_ids`。
   - 保留现有 `/api/mcp/render` 兼容路径，可内部改用新 gateway。

### 8.4 前端任务

1. 输入区增加上传控件。
2. 上传后显示附件列表。
3. 发送聊天时附带 `file_ids`。
4. SSE final 事件解析 `artifacts`。
5. 新增 artifact iframe 面板。
6. 支持多个 artifact 同时展示。
7. iframe 失败时提供打开新窗口降级。

### 8.5 第一验收标准

以下场景可正常工作:

```text
上传 CIF，输入“把这个结构可视化”
  -> 生成 structure artifact，iframe 展示。

上传 dos.txt，输入“画 DOS”
  -> 生成 dos artifact，iframe 展示。

上传 xrd.txt，输入“画 XRD”
  -> 生成 xrd artifact，iframe 展示。

上传两个文件，输入“分别画 DOS 和 XRD”
  -> 同时生成两个 artifacts。

上传 xlsx，输入“这是二元相图，帮我画出来”
  -> 生成 binary_phase artifact。
```

错误场景:

```text
上传 pdf，输入“直接画 DOS”
  -> 不应强行调用 dos.dos_file，应提示 PDF 不是直接可视化数据文件。

上传 txt，用户没有说明 DOS 还是 XRD
  -> 应提示需要明确 intent，或让 LLM 根据文件名/上下文谨慎判断。

MCP 返回无 render_url
  -> 返回清晰错误，不应让前端空白。
```

---

## 九、第二期开发范围

### 9.1 目标

在第一期稳定后，扩展为更完整的工具生态:

```text
更多 MCP 类型 + 文档/图片上下文理解 + URL 提取 + iframe 兼容性验证 + 工具发现辅助
```

### 9.2 新增 MCP 工具

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

`dw3` 和 `yxty3` 还有 `_dual`、`_mass` 变体。第二期可以增加 intent 参数:

```text
composition_basis = atom | mass
mode = single | dual
```

后端再选择:

```text
dw3.isothermal_xlsx_file
dw3.isothermal_xlsx_file_dual
dw3.isothermal_xlsx_file_mass
```

### 9.3 文档和图片理解

第二期处理 `.pdf`、`.doc`、`.docx`、`.jpg`、`.png`:

#### PDF/DOC/DOCX

目标:

- 提取文本。
- 提取 URL。
- 提取表格摘要。
- 作为 LLM 上下文辅助判断用户意图。

可行路径:

```text
PDF -> 文本提取 -> 找出 http(s) 数据文件 URL -> 调用 MCP *_url 工具。
DOC/DOCX -> 文本/表格提取 -> 找出材料数据说明或 URL。
```

暂不建议第一时间做:

```text
PDF 截图/论文图 -> 自动还原成 DOS/XRD 原始数据
```

这类任务精度风险高，应作为后续研究功能。

#### JPG/PNG

目标:

- OCR 或视觉模型理解图片内容。
- 判断是否是 DOS/XRD/相图截图。
- 给出解释或要求用户提供原始数据文件。

第一版不建议从图片反推原始曲线数据并调用 MCP。

### 9.4 URL 工具

第二期加强 URL 输入:

```text
用户: 用这个链接里的 XRD 数据画图 http://...
```

流程:

```text
LLM -> render_with_mcp(input_type=url, intent=xrd, http_url=...)
Router -> x_ray.xrd_url
MCP -> render_url
Artifact -> iframe
```

后端校验:

- URL 必须是 http/https。
- 可选: 禁止 localhost、内网 IP，避免 SSRF。
- URL 后缀与 intent 尽量匹配。

### 9.5 工具发现辅助

第二期可以增加后台管理接口:

```text
GET /api/mcp/servers
GET /api/mcp/servers/{server}/tools
```

用途:

- 检查 `server_json` 是否加载成功。
- 展示每个 server 的 tools/list。
- 帮助维护路由表。

注意: 这不等于让 LLM 动态调用任意工具。生产路径仍使用白名单路由。

### 9.6 第二期验收标准

```text
上传 zip，输入“画能带”
  -> 生成 band artifact。

上传 vtp，输入“显示这个 VTP 模型”
  -> 生成 vtp artifact。

上传 PDF，输入“找出里面的数据链接并画 XRD”
  -> 系统能提取 URL 并调用 x_ray.xrd_url，或说明未找到可用 URL。

输入远程 URL，要求生成 DOS/XRD/相图
  -> 调用对应 *_url 工具。

同一次对话生成 3 个以上 artifact
  -> 前端稳定展示，不覆盖旧结果。
```

---

## 十、安全与风险

### 10.1 文件上传风险

必须限制:

- 上传大小。
- 后缀白名单。
- 文件保存目录。
- 文件名规范化。
- 禁止通过 file_id 读取上传目录外文件。

### 10.2 远程 MCP 数据外传风险

调用 `*_file` 工具会把文件内容 base64 发送到远程 MCP server。系统需要:

- 在 UI 或配置中明确这是远程可视化调用。
- 只对用户上传文件或系统生成文件调用。
- 不把任意本地路径交给 MCP。
- 记录调用 server/tool/file_id，便于审计。

### 10.3 iframe 风险

风险:

- 远程页面禁止 iframe。
- 远程页面加载慢或失败。
- 远程页面样式不适配容器。

降级:

- 打开新窗口。
- 显示 render_url。
- 后端记录 iframe 兼容性状态。

### 10.4 LLM 误判风险

例如 `.txt` 可能是 DOS，也可能是 XRD。应采用:

- intent 明确时才调用。
- 文件名和用户语言共同判断。
- 不确定时让 LLM 追问。
- 后端后缀校验阻止明显错误调用。

---

## 十一、测试计划

### 11.1 后端单元测试

新增测试:

```text
tests/test_mcp_registry.py
tests/test_mcp_router.py
tests/test_upload_store.py
tests/test_mcp_gateway.py
tests/test_workflow_mcp_artifacts.py
```

覆盖:

- 加载 server_json。
- 缺失配置时报错。
- intent 到 server/tool 的路由。
- 后缀不匹配时报错。
- file_id 路径逃逸防护。
- plain JSON 和 SSE JSON 响应解析。
- render_url 提取。
- 多 artifact 聚合。

### 11.2 后端集成测试

使用 mock MCP server，不在 CI 中访问真实远程服务:

```text
tools/list -> 返回工具列表
tools/call -> 返回 {"render_url": "http://example.test/view"}
```

验证:

- `/api/files/upload`
- `/api/chat`
- `/api/mcp/render`

### 11.3 前端测试

覆盖:

- 文件上传成功显示附件 chip。
- 发送消息携带 file_ids。
- 多 artifact 渲染。
- iframe fallback 显示“打开新窗口”。
- 移动端布局不重叠。

---

## 十二、实施顺序

### 第一期建议顺序

1. 后端配置和 registry。
2. 通用 MCP gateway。
3. 上传文件 store 和 API。
4. MCP router 和第一批 route。
5. `render_with_mcp` LLM 工具。
6. `WorkflowContext.artifacts` 和 SSE final 扩展。
7. 前端上传控件。
8. 前端 artifact iframe 面板。
9. 后端测试和前端 smoke 测试。

### 第二期建议顺序

1. 扩展 route table。
2. URL 工具调用。
3. PDF/DOC 文本和 URL 提取。
4. JPG/PNG OCR 或视觉理解。
5. MCP 管理/诊断接口。
6. iframe 兼容性探测和降级优化。
7. 更多端到端场景测试。

---

## 十三、兼容策略

### 13.1 保留现有 3DGS MCP

现有 `3DGS MCP` 不应被替换。它可以作为 artifacts 的一种来源:

```json
{
  "kind": "mcp_visualization",
  "source": "3dgs:mcp",
  "display": "iframe",
  "render_url": "http://127.0.0.1:8090/viewer/sessions/..."
}
```

这样前端统一显示:

```text
3DGS artifact
远程 DOS artifact
远程 XRD artifact
远程相图 artifact
```

### 13.2 保留旧字段 viz

短期保留:

```json
{
  "viz": {...},
  "artifacts": [...]
}
```

前端逐步迁移为优先使用 `artifacts`。当所有可视化都走 artifact 后，再考虑弱化 `viz`。

---

## 十四、开放问题

1. 真实远程 `render_url` 是否允许 iframe 嵌入，需要实际调用后验证。
2. 远程 MCP 返回的 `render_url` 是否有过期时间，如果没有，需要本系统设置默认 TTL。
3. PDF/DOC/JPG 是否只作为上下文，还是后续要支持自动抽取曲线数据。
4. 上传文件是否需要用户级隔离和登录态绑定。
5. 是否需要在 UI 中明确提示“该文件将发送到远程 MCP 服务进行渲染”。

---

## 十五、第一版最小闭环总结

第一版不要试图一次解决所有文件和所有 MCP 工具。最小闭环是:

```text
上传文件
LLM 识别 intent
后端白名单路由
调用 fz/dos/xrd/hot2/hot3
返回 artifacts[]
前端多个 iframe 同时展示
```

这个闭环跑通后，新的 MCP server 就可以作为系统工具扩展持续添加，而不需要重写前端展示逻辑或让用户理解工具细节。
