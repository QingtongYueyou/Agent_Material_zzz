# Fix Plan: Code Review Findings for frontend-ui-optimization

## Context

Code review of the `frontend-ui-optimization` branch identified 6 bugs and 3 concerns in the materials science analysis app. This plan fixes them in priority order.

## Changes

### 1. Bug: Search tool errors silently treated as success

**Problem:** `search_materials_by_criteria_raw` returns error strings (`"未找到..."`) but `workflow.py` only detects errors via `isinstance(result_payload, dict)` — strings skip detection, tool is marked SUCCESS.

**Fix:** Add string-based error detection to the tool result loop in `workflow.py`.

**Files:**
- `core/workflow.py` — In the tool result loop (after `execute_openai_tool` at ~line 337), add: detect when `result_payload` is a string that starts with known error patterns ("Error:", "未找到", "系统错误", "参数类型错误", "搜索 API 调用出错"), OR more robustly: make `search_materials_by_criteria_raw` return dicts like `{"ok": false, "error": "..."}` instead of plain strings.
  - **Approach:** Refactor `search_materials_by_criteria_raw` to return a dict `{"ok": false, "error": "..."}` or `{"ok": true, "data": [...]}` consistently, so the existing `isinstance(result, dict)` check at line 350 catches it.

### 2. Bug: Frontend `answer_delta` event handler is dead code

**Problem:** Frontend has full `answer_delta` handling (App.tsx:108-127), backend never emits it. ~20 lines dead code.

**Fix:** Two options. Pick the pragmatic one: **Remove the dead code**. Remove `answer_delta` from the frontend type union and delete the handler. If streaming output is desired later, implement it properly then.

**Files:**
- `frontend/src/types.ts` — Remove `"answer_delta"` from the `type` union in `WorkflowEvent`
- `frontend/src/App.tsx` — Remove the `event.type === "answer_delta"` handler block (lines 108-127)

### 3. Bug: Answer not validated against known facts

**Problem:** Removed `_validate_answer_against_facts` checked LLM answer contains correct `formula` and `mp_id`. Current code trusts LLM output entirely.

**Fix:** Add validation back to `_final_answer_from_context`.

**Files:**
- `core/workflow.py` — After `_final_answer_from_context` returns, add a validation step:
  - If `ctx.structure_result` has `formula`/`mp_id`, check the answer string contains them
  - If not found (or extra mp-ids appear), fall back to `_fallback_answer` instead

### 4. Bug: No primary-button check in 3D viewer

**Problem:** `handlePointerDown` in SplatViewer doesn't filter `event.button`, so right-click and middle-click trigger orbit drag and record metrics.

**Fix:** Add `if (event.button !== 0) return;` at top of `handlePointerDown`.

**Files:**
- `frontend/src/components/SplatViewer.tsx` — Line ~294, add button filter

### 5. Concern: Search API fetches chunk_size=1000 unconditionally

**Problem:** `chunk_size` hardcoded to 1000 even when `max_results=5`, wasting API quota.

**Fix:** Set `chunk_size = max(chunk_size, max_results)` or `min(max_results, 1000)`.

**Files:**
- `core/tools.py` — Line ~122, derive `chunk_size` from `max_results`

### 6. Concern: `search_materials_by_criteria_raw` returns mixed types

**Problem:** Returns strings on error, JSON string on success. Caller must know the internals to parse.

**Fix:** Already addressed by fix #1 — refactor to return dict `{"ok": true/false, "data": [...], "error": "..."}`.

**Files:**
- `core/tools.py` — `search_materials_by_criteria_raw` return type change

### 7. Concern: No input length/content validation

**Problem:** `ChatRequest.query` only has `min_length=1`, no `max_length`.

**Fix:** Add `max_length` to the query field.

**Files:**
- `api/schemas.py` — Add `max_length=10000` or similar

### 8. Future consideration: No multi-turn conversation

**Problem:** Each `run_stream` creates fresh messages list, no history passed to LLM.

**Fix:** Out of scope for this PR. Document in a memory note.

## Verification

1. **Run `python check_llm.py`** — verify the app's LLM connectivity (if the check script still exists, or use `python -c "from core.llm_client import chat_completion; print(chat_completion([{'role':'user','content':'hi'}], max_tokens=10))"`)
2. **Run backend tests:** `python -m pytest tests/ -v` (or `python -m unittest discover tests -v`)
3. **Start backend:** `uvicorn api.main:app --host 127.0.0.1 --port 8080` and verify `GET /health` returns ok
4. **Smoke test search error path:** Send `POST /api/chat` with `{"query": "zzzznonmaterial"}` — verify the trace panel shows a failure, not success
5. **Frontend build:** `cd frontend && npm run build` — verify no TypeScript errors
6. **Manual check** the 3D viewer doesn't respond to right-click drag