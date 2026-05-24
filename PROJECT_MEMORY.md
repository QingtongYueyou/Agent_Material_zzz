# Project Memory

## Current Architecture

This project is now a separated FastAPI + React materials analysis application.

- Project root: `D:\wyfzzz\PyCharm\MyProjects\Agent_Material\mytest\Agent`
- Backend entry: `api/main.py`
- Frontend entry: `frontend/src/App.tsx`
- Branch for this work: `frontend-ui-optimization`

## Runtime

Backend:

```bash
uvicorn api.main:app --host 127.0.0.1 --port 8080
```

Frontend:

```bash
cd frontend
npm install
npm run dev
```

The Vite dev server proxies `/api`, `/health`, and `/static` to `http://127.0.0.1:8080`.

## Main Flow

1. React sends a user query to `POST /api/chat/stream`.
2. FastAPI calls `WorkflowOrchestrator.run_stream()`.
3. `core/workflow.py` uses LLM function calling and `core/tools.py`.
4. Materials Project results are saved as CIF files in `cif_files/`.
5. `core/processor.py` converts CIF files into lattice, composition, and XRD data.
6. `api/serialization.py` converts workflow events and DataFrames into JSON.
7. React renders the answer, step trace, charts, Spark/3DGS view, and optional MCP iframe.

## Important Modules

- `api/main.py`: FastAPI app, chat stream, splat asset endpoint, MCP render endpoint, metrics endpoints.
- `api/serialization.py`: JSON-safe conversion for workflow events and visualization payloads.
- `api/schemas.py`: request models.
- `core/workflow.py`: primary orchestration path.
- `core/tools.py`: Materials Project tools and OpenAI tool specs.
- `core/processor.py`: CIF parsing and chart data generation.
- `core/splat_assets.py`: manifest-first 3DGS/Spark asset resolution.
- `core/mcp_client.py`: MCP JSON-RPC client.
- `frontend/src/App.tsx`: application shell and stream event handling.
- `frontend/src/components/`: chat, trace, visualization, charts, 3DGS, MCP components.

## Removed Paths

- Streamlit app entry (`app.py`) and `ui/` components were removed.
- Server-B Planner API was removed.
- `core/planner.py`, `core/planner_schema.py`, Planner docs, and Planner tests were removed.
- Legacy Agno compatibility files (`material_chatbot.py`, `core/agent.py`) were removed.
- Old fixed-step workflow files (`core/steps.py`, `core/answer_generator.py`) were removed.
- Old standalone 3D conversion script (`3DGS_test.py`) and the repo-local `cloudflared.exe` binary were removed.
- `PLAN_API_TOKEN` is no longer used.

## Environment Variables

- `MP_API_KEY` or `MAPI_KEY`
- `POE_API_KEY`
- `POE_API_BASE_URL`
- `LLM_MODEL_ID`
- `LLM_TIMEOUT_SEC`
- `MCP_ENABLED`
- `MCP_SERVER_URL`
- `MCP_API_KEY`
- `MCP_TIMEOUT_SEC`
- `MCP_RENDER_TTL_SEC`
- `SPARK_ROOT`
- `SPARK_AUTO_INGEST`
- `SPARK_AUTO_VARIANT`

## Maintenance Notes

- Keep backend responses JSON-safe; do not return Pandas DataFrames directly.
- Keep 3D assets under `static/splat_files/` and resolve them through `core/splat_assets.py`.
- If the frontend needs additional workflow data, add it in `api/serialization.py` rather than leaking Python objects.
