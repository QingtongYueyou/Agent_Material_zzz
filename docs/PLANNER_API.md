# Planner API

This project can run as server B: a lightweight LLM planner service that converts server A's natural-language user instruction into executable JSON tool calls.

Server B does not query server A's database, retrieve files, push WebSocket messages, render UI, or generate the final user-facing answer. Server A owns those steps.

## Start Locally

Use the existing conda test environment:

```powershell
conda activate agno-assist
uvicorn api.main:app --host 127.0.0.1 --port 8000
```

Health check:

```powershell
curl http://127.0.0.1:8000/health
```

If conda activation is unavailable in the current shell, use the environment Python directly:

```powershell
C:\Users\wyfz\.conda\envs\agno-assist\python.exe -m uvicorn api.main:app --host 127.0.0.1 --port 8000
```

## Optional Auth

Set a shared token in `.env`:

```env
PLAN_API_TOKEN=replace-with-a-shared-secret
```

When `PLAN_API_TOKEN` is set, server A must call the API with:

```http
Authorization: Bearer replace-with-a-shared-secret
```

## Plan Endpoint

```http
POST /api/v1/plan
Content-Type: application/json
Authorization: Bearer replace-with-a-shared-secret
```

Request:

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

Response:

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

If the LLM is unavailable or returns invalid JSON, server B returns a conservative rule-based fallback with `planner_meta.source` starting with `fallback:`.

## HTTPS Tunnel for Local Deployment

For development, expose the local API with Cloudflare Tunnel:

```powershell
cloudflared tunnel --url http://127.0.0.1:8000
```

Cloudflare returns an HTTPS URL such as:

```text
https://example.trycloudflare.com
```

Give server A:

- Base URL: `https://example.trycloudflare.com`
- Plan endpoint: `POST https://example.trycloudflare.com/api/v1/plan`
- Shared bearer token: the value of `PLAN_API_TOKEN`

## Server A Responsibilities

Server A should:

1. Forward user natural language to server B.
2. Parse `tool_calls`.
3. Execute database lookup and file retrieval.
4. Push visualization payloads to the frontend through WebSocket.
5. Generate or assemble the final user-facing answer.
