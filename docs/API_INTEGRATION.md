# Agent Material API 接入说明

本文档面向调用 Agent Material API 的第三方系统开发者。服务默认已经部署完成，调用方只需通过 HTTP 提交自然语言和可选材料文件，系统会自动识别意图、选择对应的 MCP 工具，并返回可视化地址。

## 1. 接入信息

| 项目 | 说明 |
| --- | --- |
| 服务地址 | 由平台方提供，例如 <code>https://agent-material.example.com</code> |
| 普通请求 | HTTPS + JSON |
| 文件上传 | <code>multipart/form-data</code> |
| 流式响应 | SSE（<code>text/event-stream</code>） |
| OpenAPI | <code>{BASE_URL}/openapi.json</code> |
| 在线调试 | <code>{BASE_URL}/docs</code> |

当前应用接口本身没有统一的 API Key 校验。如果部署环境通过 API Gateway 提供了认证，请按平台方要求增加 <code>Authorization</code> 等请求头。

## 2. 推荐调用流程

~~~text
有文件：上传文件 → 获得 file_id → 提交自然语言和 file_id → 获得 render_url
无文件：直接提交自然语言 → Agent 查询或生成所需数据 → 获得文本或可视化结果
~~~

面向最终用户时，推荐调用 <code>POST /api/chat</code>。调用方不需要让用户选择 MCP，也不需要了解 MCP Server 和 Tool 名称。

## 3. 上传文件

如果用户提供文件，先调用：

~~~http
POST /api/files/upload
Content-Type: multipart/form-data
~~~

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| <code>file</code> | binary | 是 | 用户选择的材料数据文件 |

请求示例：

~~~bash
curl -X POST "{BASE_URL}/api/files/upload" -F "file=@sample.dat"
~~~

响应示例：

~~~json
{
  "file_id": "file_20260814_0123456789abcdef",
  "filename": "sample.dat",
  "extension": ".dat",
  "mime_type": "application/octet-stream",
  "size_bytes": 18432,
  "sha256": "c01d...9af2",
  "created_at": 1786672800.123,
  "source": "user_upload"
}
~~~

调用方保存 <code>file_id</code> 即可，后续请求不要传服务器文件路径。

默认支持：

~~~text
.cif .xyz .poscar .cell .pdb .dat .txt .xls .xlsx .zip
.vtp .stl .glb .dump .cfg .data .lmp
~~~

默认单文件上限为 100 MiB。一个智能调用请求最多携带 10 个 <code>file_id</code>。

## 4. 智能调用

### 4.1 同步调用

~~~http
POST /api/chat
Content-Type: application/json
~~~

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| <code>query</code> | string | 是 | 用户自然语言，长度 1～10000 个字符 |
| <code>file_ids</code> | string[] | 否 | 上传后的文件标识，默认 <code>[]</code>，最多 10 个 |

有文件示例：

~~~json
{
  "query": "这是 DOS 态密度数据，请生成可交互的 DOS 图。",
  "file_ids": ["file_20260814_0123456789abcdef"]
}
~~~

同一种扩展名可能对应多种能力。例如 <code>.dat</code> 可能是 DOS、XRD、相图曲线或分子动力学数据，因此自然语言中应尽量说明文件内容。

无文件示例：

~~~json
{
  "query": "请查询 mp-1661648 的晶体结构，并生成交互式结构可视化。",
  "file_ids": []
}
~~~

无文件请求依赖系统能否查询或生成所需数据。如果缺少必要输入，Agent 可能只返回文字说明或要求用户补充信息。

响应包含完整过程 <code>events</code> 和最终结果 <code>final</code>。<code>final</code> 示例：

~~~json
{
  "type": "final",
  "trace_id": "e91981f5-8b15-4cc0-a645-392cd4d19830",
  "answer": "已根据 DOS 数据生成可视化结果。",
  "artifacts": [
    {
      "id": "artifact_0123456789ab",
      "kind": "mcp_visualization",
      "title": "DOS 可视化",
      "intent": "dos",
      "display": "iframe",
      "render_url": "https://visualization.example/render/temporary-token",
      "source_file_id": "file_20260814_0123456789abcdef",
      "provider": "dos-mcp-server",
      "tool": "dos.dos_file"
    }
  ],
  "step_results": []
}
~~~

调用方重点处理：

| 字段 | 说明 |
| --- | --- |
| <code>final.answer</code> | 展示给用户的最终文字 |
| <code>final.artifacts</code> | 可视化结果列表，可能为空或包含多个结果 |
| <code>final.artifacts[].render_url</code> | 可视化页面地址 |
| <code>final.artifacts[].display</code> | 当前一般为 <code>iframe</code> |
| <code>final.trace_id</code> | 日志关联和问题排查标识 |

不要依赖 <code>events</code> 的固定数量或固定顺序。

### 4.2 流式调用

需要实时显示执行进度时，使用：

~~~http
POST /api/chat/stream
Content-Type: application/json
Accept: text/event-stream
~~~

请求体与 <code>/api/chat</code> 相同。每条 SSE 消息格式如下：

~~~text
data: {"type":"step_start","step":"function_calling"}

data: {"type":"step_end","step":"render_with_mcp","status":"success"}

data: {"type":"final","trace_id":"...","answer":"...","artifacts":[...]}
~~~

出现以下事件表示执行失败：

~~~json
{
  "type": "error",
  "detail": "Downstream MCP request failed",
  "error_type": "MCPClientError"
}
~~~

智能接口可能返回 HTTP <code>200</code>，但事件中包含 <code>type: error</code>。同步和流式调用都应检查错误事件，不能只检查 HTTP 状态码。

## 5. 指定能力调用

如果调用方已经明确知道目标能力，可以不经过 LLM：

~~~http
POST /api/visualizations/render
Content-Type: application/json
~~~

文件类能力请求：

~~~json
{
  "intent": "xrd",
  "input_type": "file",
  "file_id": "file_20260814_0123456789abcdef"
}
~~~

响应示例：

~~~json
{
  "ok": true,
  "id": "artifact_0123456789ab",
  "kind": "mcp_visualization",
  "title": "XRD 可视化",
  "intent": "xrd",
  "display": "iframe",
  "render_url": "https://visualization.example/render/temporary-token",
  "source_file_id": "file_20260814_0123456789abcdef",
  "provider": "x-ray-mcp-server",
  "tool": "x_ray.xrd_file"
}
~~~

渲染服务端已有的 3DGS 资产：

~~~json
{
  "intent": "3dgs",
  "input_type": "asset",
  "filename": "mp-1661648_LiFePO4.ply",
  "quality": "balanced",
  "render_profile": "performance"
}
~~~

<code>quality</code> 可选值为 <code>auto</code>、<code>preview</code>、<code>balanced</code>、<code>full</code>、<code>source</code>；<code>render_profile</code> 可选值为 <code>performance</code>、<code>quality</code>。

## 6. 查询可视化能力

~~~http
GET /api/visualizations/capabilities
~~~

响应示例：

~~~json
{
  "capabilities": [
    {
      "intent": "dos",
      "title": "DOS 可视化",
      "provider": "dos-mcp-server",
      "tool": "dos.dos_file",
      "input_type": "file",
      "extensions": [".dat", ".txt"],
      "enabled": true
    }
  ]
}
~~~

当前能力包括：

| intent | 能力 | 主要输入 |
| --- | --- | --- |
| <code>3dgs</code> | 3D Gaussian Splatting | 服务端 3DGS 资产 |
| <code>structure</code> | 晶体/分子结构 | CIF、XYZ、POSCAR、CELL、PDB |
| <code>dos</code> | DOS 态密度 | DAT、TXT |
| <code>xrd</code> | XRD | DAT、TXT |
| <code>binary_phase</code> / <code>ternary_phase</code> | 二元/三元相图 | XLS、XLSX |
| <code>band</code> | 能带 | ZIP |
| <code>vtp</code> | VTP 模型 | VTP |
| <code>model</code> | 三维模型 | STL、GLB |
| <code>molecular_dynamics</code> | 分子动力学 | DUMP、CFG、DATA、DAT、LMP、XYZ |
| <code>phase_curve</code> | 相图曲线 | DAT、TXT |
| <code>liquidus*</code> | 液相面 | XLS、XLSX |
| <code>isothermal*</code> | 等温截面 | XLS、XLSX |
| <code>vertical_section</code> | 垂直截面 | XLS、XLSX |

完整 <code>intent</code>、支持格式和启用状态，应以 capabilities 接口的实时返回为准。

## 7. 展示可视化结果

取得 <code>render_url</code> 后，可以通过 iframe 展示：

~~~html
<iframe
  title="材料可视化"
  src="https://visualization.example/render/temporary-token"
  style="width: 100%; height: 720px; border: 0"
  allowfullscreen
></iframe>
~~~

注意：

- <code>render_url</code> 可能是绝对地址，也可能是相对 Agent Material 服务的路径；
- 可视化 URL 可能包含临时令牌并具有有效期，过期后应重新渲染；
- 不要把完整临时 URL、用户文件内容或认证信息写入公开日志。

## 8. Python 完整示例

~~~python
from pathlib import Path
from urllib.parse import urljoin

import httpx


BASE_URL = "https://agent-material.example.com"
FILE_PATH = Path("sample.dat")

with httpx.Client(timeout=180.0) as client:
    with FILE_PATH.open("rb") as file_handle:
        response = client.post(
            f"{BASE_URL}/api/files/upload",
            files={"file": (FILE_PATH.name, file_handle)},
        )
    response.raise_for_status()
    file_id = response.json()["file_id"]

    response = client.post(
        f"{BASE_URL}/api/chat",
        json={
            "query": "这是 DOS 态密度数据，请生成可交互的 DOS 图。",
            "file_ids": [file_id],
        },
    )
    response.raise_for_status()
    payload = response.json()

    errors = [
        event for event in payload.get("events", [])
        if event.get("type") == "error"
    ]
    if errors:
        raise RuntimeError(errors[-1].get("detail", "Agent execution failed"))

    final = payload.get("final") or {}
    artifacts = final.get("artifacts") or []
    if not artifacts:
        raise RuntimeError(final.get("answer") or "No visualization was generated")

    render_url = urljoin(f"{BASE_URL}/", artifacts[0]["render_url"])
    print(render_url)
~~~

## 9. 错误处理

| HTTP 状态码 | 说明 | 处理建议 |
| --- | --- | --- |
| <code>400</code> | 文件、intent 或输入类型不符合要求 | 修改请求，不直接重试 |
| <code>404</code> | 资产不存在 | 检查资产文件名 |
| <code>422</code> | 缺少字段或字段值无效 | 根据 <code>detail</code> 修改请求 |
| <code>500</code> | Agent Material 内部错误 | 记录请求时间和路径，联系平台方 |
| <code>502</code> | 下游 MCP 调用失败 | 稍后有限次数重试 |
| <code>503</code> | 对应 MCP 能力暂不可用 | 查询 capabilities 或联系平台方 |

建议客户端总超时设置为 120～180 秒。渲染接口目前不支持幂等键，网络失败后的自动重试可能创建重复渲染会话。

## 10. 接口汇总

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| GET | <code>/health</code> | 检查服务状态 |
| GET | <code>/api/visualizations/capabilities</code> | 查询可视化能力 |
| POST | <code>/api/files/upload</code> | 上传材料文件 |
| POST | <code>/api/chat</code> | 自然语言同步调用 |
| POST | <code>/api/chat/stream</code> | 自然语言流式调用 |
| POST | <code>/api/visualizations/render</code> | 指定能力直接渲染 |

第三方新系统应优先使用以上接口。