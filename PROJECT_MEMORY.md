# Project Memory

This file is the project-level memory for future assistant sessions. Read it first when working in this repository, and update it whenever architectural or behavioral changes are made.

## Repository Root

- Actual Git/project root: `D:\wyfzzz\PyCharm\MyProjects\Agent_Material\mytest\Agent`
- Parent folder `Agent_Material` is not a Git repository.

## Project Purpose

This is a Streamlit-based intelligent materials analysis application for materials science workflows. It accepts natural-language questions, uses an LLM to decide which materials tools to call, queries Materials Project, saves CIF files, parses crystal structure data, renders 3D/plot visualizations, and generates Chinese final answers.

Primary launch command:

```bash
streamlit run app.py
```

The project also supports a server-B planner API for integration with an external server A:

```bash
uvicorn api.main:app --host 127.0.0.1 --port 8000
```

Planner docs: `docs/PLANNER_API.md`

## Main Runtime Path

- `app.py` is the Streamlit entry point.
- Current active workflow is `core/workflow.py` via `WorkflowOrchestrator`.
- `core/steps.py` is an older/fallback fixed-step workflow and is not the main path used by `app.py`.
- `material_chatbot.py` and `core/agent.py` keep the older Agno agent path.
- `api/main.py` exposes the FastAPI planner service (`GET /health`, `POST /api/v1/plan`) for server A integration.
- `core/planner.py` converts natural-language materials requests into strict JSON tool calls for server A.
- `core/planner_schema.py` defines the server-A tool-call contract and validation/cleanup helpers.

Current user flow:

1. User enters a question in the left chat panel.
2. `app.py` creates `WorkflowOrchestrator`.
3. `WorkflowOrchestrator.run_stream()` calls the Poe/OpenAI-compatible chat completions endpoint.
4. The LLM uses function calling to decide between:
   - `search_materials_by_criteria`
   - `get_mp_structure`
5. `core/tools.py` calls Materials Project through `mp_api.client.MPRester`.
6. Structure retrieval writes a CIF file to `cif_files/`.
7. `core/processor.py` parses the CIF with pymatgen and creates DataFrames for lattice parameters, composition, and simulated XRD.
8. `ui/visualization.py` renders the 3DGS/WebGL panel plus Altair charts.
9. Final answer is generated from structured facts; if LLM generation fails, a template fallback is used.

Server-B planner flow:

1. Server A sends `POST /api/v1/plan` with a user query and optional context.
2. `api/main.py` optionally checks `PLAN_API_TOKEN`.
3. `core/planner.py` calls the LLM through `core/llm_client.py`.
4. The planner returns strict JSON tool calls such as `material.get_structure_file` and `visualization.render_xrd`.
5. Server A executes database lookup, file retrieval, WebSocket push, visualization, and final answering.

## Key Modules

- `config/settings.py`
  - Loads `.env`.
  - Defines project paths, metrics paths, API keys, LLM model id, and timeout.
  - Important env vars: `MP_API_KEY` or `MAPI_KEY`, `POE_API_KEY`, `POE_API_BASE_URL`, `LLM_MODEL_ID`, `LLM_TIMEOUT_SEC`, `PLAN_API_TOKEN`.
  - Do not expose `.env` contents in summaries or commits.

- `core/tools.py`
  - `get_mp_structure_raw(identifier)` retrieves an mp-id or exact formula, extracts space group/crystal system, writes CIF, and returns metadata.
  - `search_materials_by_criteria_raw(...)` searches Materials Project by elements, band gap, stability, crystal system, and result count.
  - `OPENAI_TOOL_SPECS` defines OpenAI-compatible function schemas.
  - `execute_openai_tool(...)` dispatches LLM tool calls to the raw functions.

- `core/workflow.py`
  - Active orchestration layer.
  - Uses a function-calling loop with `MAX_TOOL_ROUNDS = 6`.
  - Sanitizes tool results by removing raw CIF before sending back into context.
  - Updates `WorkflowContext` with retrieval, structure, and visualization data.
  - Emits Streamlit-facing events: `step_start`, `step_end`, `final`.
  - Generates final Chinese answers from factual context and falls back to templates on failure.

- `core/processor.py`
  - Uses pymatgen to parse CIF.
  - Returns lattice DataFrame, composition DataFrame, and simulated XRD DataFrame.
  - XRD uses CuKa wavelength and keeps peaks up to 70 degrees 2Theta.

- `core/llm_client.py`
  - Lightweight urllib wrapper for OpenAI-compatible `/chat/completions`.
  - Supports tools and tool choice.
  - Raises `LLMClientError`.
  - Some error strings appear encoding-damaged and may need cleanup.

- `core/answer_generator.py`
  - Used mainly by the older fixed-step flow.
  - Contains intent classification, final answer generation, and answer/material-id consistency validation.

- `core/planner.py`
  - Server-B natural-language planner.
  - Calls the LLM to produce strict JSON tool calls for server A.
  - Falls back to a conservative rule-based plan if the LLM is unavailable or emits invalid JSON.

- `core/planner_schema.py`
  - Defines available server-A tools and their allowed argument keys.
  - Cleans and validates LLM-emitted tool calls.

- `api/main.py`
  - FastAPI app exposing `GET /health` and `POST /api/v1/plan`.
  - Uses `PLAN_API_TOKEN` as optional Bearer-token auth.

- `ui/chat.py`
  - Left chat panel and input.

- `ui/components.py`
  - Top bar, right-side execution trace, data summary, debug sidebar.

- `ui/visualization.py`
  - Middle visualization panel.
  - Starts a local CORS-enabled static/metrics HTTP server, default port `8001`.
  - Renders Gaussian Splatting models with browser-side Three.js and `@mkkellogg/gaussian-splats-3d`.
  - Matches models from `static/splat_files` by `mp-id_formula`, `mp-id`, `formula`, glob patterns, then falls back to `object.ply`.
  - Posts render and interaction metrics back to local endpoints.
  - Renders Altair charts for lattice, composition, and XRD.

- `core/perf_metrics.py`
  - Appends render and interaction metrics to CSV files.
  - Can read vertex count from PLY headers.

- `metrics/tools/analyze_render_metrics.py`
  - Summarizes render metrics by model.

- `metrics/tools/analyze_interaction_metrics.py`
  - Summarizes interaction metrics by model and interaction type.

- `metrics/tools/merge_gaussian_ply.py`
  - Merges supported binary Gaussian PLY files and can translate inputs before concatenation.

- `3DGS_test.py`
  - Independent script for converting phase-field/voxel data into Gaussian PLY or point-cloud PLY.
  - Supports dense grid interface extraction or sparse point conversion.

## Data and Resources

- `cif_files/` stores generated or cached CIF files, including examples such as:
  - `mp-149_Si.cif`
  - `mp-1661648_LiFePO4.cif`
  - `mp-3442_CaTiO3.cif`
  - `mp-1192859_NaFePO4.cif`
- `static/splat_files/` stores large PLY/SPLAT models for 3DGS visualization.
- `metrics/raw/` stores render and interaction CSV data plus generated test PLY artifacts.
- Generated metrics and 3D model assets are intentionally ignored by Git: `metrics/raw/*.csv`, `metrics/raw/*.ply`, `static/splat_files/*.ply`, `static/splat_files/*.splat`, and `static/splat_files/*.ksplat`.
- Some PLY files are very large, especially `static/splat_files/object.ply`; keep them local or manage them through external artifact storage/Git LFS instead of normal Git.

## Known Project State Notes

- There is no `requirements.txt`, `pyproject.toml`, or `environment.yml` observed, so dependency setup is not fully reproducible.
- Important Python dependencies include `streamlit`, `mp-api`, `pymatgen`, `agno`, `pandas`, `altair`, `python-dotenv`, and `numpy`.
- Browser-side 3D rendering depends on CDN imports for Three.js and `@mkkellogg/gaussian-splats-3d`.
- Current codebase includes both the newer function-calling workflow and older Agno/fixed-step paths. Prefer the newer `core/workflow.py` path unless the user specifically asks about legacy behavior.
- Git working tree had existing user changes at the time this memory was created. Do not revert unrelated changes.

## Maintenance Rule

When making future changes:

- Update this file if the project structure, runtime path, APIs, important modules, data locations, dependencies, or major behavior changes.
- Keep this file concise and factual.
- Do not include secrets, raw `.env` contents, or large generated data dumps.
