# Planner API

本项目可作为 Server B 运行：一个轻量级 LLM 规划服务，将 Server A 的用户自然语言指令转换为可执行的 JSON 工具调用。

Server B 不负责查询数据库、检索文件、推送 WebSocket 消息、渲染 UI 或生成最终用户回答。这些步骤由 Server A 执行。

## 本地启动

使用现有的 conda 测试环境：

```powershell
conda activate agno-assist
uvicorn api.main:app --host 127.0.0.1 --port 8000
```

健康检查：

```powershell
curl http://127.0.0.1:8000/health
```

如果当前 shell 无法激活 conda，可直接使用环境 Python：

```powershell
C:\Users\wyfz\.conda\envs\agno-assist\python.exe -m uvicorn api.main:app --host 127.0.0.1 --port 8000
```

## 可选认证

在 `.env` 中设置共享令牌：

```env
PLAN_API_TOKEN=replace-with-a-shared-secret
```

设置 `PLAN_API_TOKEN` 后，Server A 调用 API 时需携带：

```http
Authorization: Bearer replace-with-a-shared-secret
```

## 规划接口

```http
POST /api/v1/plan
Content-Type: application/json
Authorization: Bearer replace-with-a-shared-secret
```

请求示例：

```json
{
  "query": "展示 LiFePO4 的晶体结构和 XRD 图谱",
  "session_id": "s-001",
  "context": {
    "available_tools": [
      "material.search",
      "material.get_structure_file",
      "visualization.render_3dgs",
      "visualization.render_lattice",
      "visualization.render_composition",
      "visualization.render_xrd"
    ]
  }
}
```

响应示例：

```json
{
  "trace_id": "uuid",
  "intent": "structure_visualization",
  "confidence": 0.93,
  "clarification_needed": false,
  "clarification_question": null,
  "tool_calls": [
    {
      "tool": "material.get_structure_file",
      "arguments": {
        "formula": "LiFePO4",
        "mp_id": null,
        "file_type": "cif"
      }
    },
    {
      "tool": "visualization.render_3dgs",
      "arguments": {
        "formula": "LiFePO4",
        "mp_id": null,
        "preferred_model": null
      }
    },
    {
      "tool": "visualization.render_lattice",
      "arguments": {}
    },
    {
      "tool": "visualization.render_composition",
      "arguments": {}
    },
    {
      "tool": "visualization.render_xrd",
      "arguments": {
        "wavelength": "CuKa"
      }
    }
  ],
  "server_a_execution_hint": {
    "requires_database_lookup": true,
    "requires_websocket_push": true,
    "final_answer_owner": "server_a"
  },
  "planner_meta": {
    "source": "llm",
    "available_tools": [
      "material.search",
      "material.get_structure_file",
      "visualization.render_3dgs",
      "visualization.render_lattice",
      "visualization.render_composition",
      "visualization.render_xrd"
    ]
  }
}
```

如果 LLM 不可用或返回无效 JSON，Server B 会返回基于规则的保守降级方案，`planner_meta.source` 以 `fallback:` 开头。

## 本地部署 HTTPS 隧道

开发阶段可使用 Cloudflare Tunnel 暴露本地 API：

```powershell
cloudflared tunnel --url http://127.0.0.1:8000
```

Cloudflare 会返回一个 HTTPS 地址，例如：

```text
https://example.trycloudflare.com
```

将以下信息提供给 Server A：

- 基础 URL：`https://example.trycloudflare.com`
- 规划接口：`POST https://example.trycloudflare.com/api/v1/plan`
- 共享令牌：`PLAN_API_TOKEN` 的值

## Server A 职责

Server A 需要：

1. 将用户自然语言转发给 Server B。
2. 解析 `tool_calls`。
3. 执行数据库查询和文件检索。
4. 通过 WebSocket 将可视化数据推送到前端。
5. 生成或组装最终的用户回答。
