# LLM File Understanding and Workflow Speed Upgrade Plan

> Date: 2026-07-02
> Goal: Let the LLM understand uploaded file contents before choosing tools, keep MP API / CIF retrieval under LLM tool control, and reduce end-to-end answer latency.

## 1. Current State

The current upload path is functional but shallow:

1. The frontend uploads files and sends `file_ids` with the chat request.
2. The backend stores uploaded files and metadata.
3. `WorkflowOrchestrator` loads only metadata into the LLM context: `file_id`, `filename`, `extension`, `size_bytes`, `source`.
4. The LLM can call `render_with_mcp(intent, input_type="file", file_id=...)`.
5. The tool reads the actual file bytes and sends base64 content to the routed MCP server.

This means the LLM can choose a tool from file names and extensions, but it does not truly inspect the file content.

The current speed bottlenecks are:

- The workflow is a serial tool loop with `MAX_TOOL_ROUNDS = 6`.
- Tool calls returned in the same LLM response are executed one by one.
- After tool calls, `_final_answer_from_context()` may call the LLM again to compose the final answer.
- MP API calls have a local `MP_MIN_REQUEST_INTERVAL_SEC = 3.0` throttle.
- Remote MCP render calls are blocking.
- File loading, metadata loading, parsing, and remote calls are not cached aggressively enough.

## 2. Target Behavior

### 2.1 Uploaded File Case

When the user uploads files, the LLM should receive a compact but useful file understanding context, for example:

```text
Uploaded file:
- file_id: file_20260702_abcd1234
  filename: dos.txt
  extension: .txt
  inferred_content_type: dos
  confidence: high
  structure:
    rows: 1200
    columns: 2
    delimiter: whitespace
    numeric_columns: 2
  signals:
    - first column looks like energy in eV
    - second column is density-like numeric data
  recommended_mcp_intents:
    - dos
```

The LLM then decides whether to call:

```json
{
  "intent": "dos",
  "input_type": "file",
  "file_id": "file_20260702_abcd1234"
}
```

If the summary is ambiguous, the LLM can call an inspection tool before rendering:

```json
{
  "file_id": "file_20260702_abcd1234",
  "detail_level": "fuller"
}
```

### 2.2 No Uploaded File Case

If the user asks about a material by mp-id, formula, or recognizable material name, the LLM should decide whether to call:

```json
{
  "identifier": "LiFePO4"
}
```

Then, if `get_mp_structure` returns a generated CIF `file_id`, the LLM can call:

```json
{
  "intent": "structure",
  "input_type": "file",
  "file_id": "file_20260702_generatedabcd"
}
```

The backend still enforces route safety. The LLM chooses intent and file id, not MCP server names or remote tool names.

## 3. File Understanding Design

### 3.1 New Module

Add:

```text
core/file_introspection.py
```

Responsibilities:

- Safely read uploaded/system-generated files by `file_id`.
- Extract structured summaries.
- Infer likely content type and recommended MCP intents.
- Cache summaries by `sha256` and parser version.
- Avoid sending large raw files into the LLM context.

### 3.2 First Supported File Types

First version should cover:

- `.cif`
- `.txt`
- `.dat`
- `.csv`
- `.xlsx`
- `.xls`

This matches the immediate MCP workflows: structure, DOS, XRD, phase curves, and phase diagrams.

### 3.3 Parsing Rules

#### CIF

Use `pymatgen` when possible.

Extract:

- formula
- reduced formula
- lattice parameters
- crystal system
- space group symbol and number
- atom count
- element list
- parse warnings

Recommended intent:

- `structure`

#### TXT / DAT

Use bounded text reads. Do not load unbounded files into memory.

Extract:

- encoding guess
- line count estimate
- delimiter guess
- header lines
- data rows sampled from head/middle/tail
- column count
- numeric column count
- min/max for numeric columns
- monotonicity of first column
- common labels such as `Energy`, `E(eV)`, `DOS`, `2theta`, `Intensity`, `q`, `phase`

Intent inference examples:

- `dos`: first column energy-like, second/third columns density-like, labels mention DOS.
- `xrd`: labels mention `2theta`, `theta`, `intensity`, or first numeric column is in a plausible diffraction range.
- `phase_curve`: text looks like temperature/composition/property curve but not DOS/XRD.

If confidence is low, return multiple candidates and mark `needs_clarification=true`.

#### CSV

Use Python `csv` or pandas with row limits.

Extract:

- header
- delimiter
- row count estimate
- column names
- inferred dtypes
- numeric ranges
- first 10 rows

Recommended intents:

- `dos`, `xrd`, or `phase_curve` depending on columns.

#### XLS / XLSX

Use `openpyxl` for `.xlsx`; use available Excel reader support for `.xls` if present, otherwise return a clear unsupported-reader warning.

Extract:

- workbook sheet names
- per-sheet used range
- column names
- first rows
- numeric density
- whether data looks binary/ternary/isothermal/liquidus/vertical section

Recommended intents:

- `binary_phase`
- `ternary_phase`
- `liquidus`
- `isothermal`
- `vertical_section`

### 3.4 Summary Shape

Use one stable JSON shape internally:

```python
{
    "file_id": "...",
    "filename": "...",
    "extension": ".txt",
    "sha256": "...",
    "parser_version": "file-introspection-v1",
    "summary_level": "default",
    "content_kind": "tabular_numeric",
    "inferred_content_type": "dos",
    "confidence": "high",
    "recommended_mcp_intents": ["dos"],
    "needs_clarification": False,
    "facts": {...},
    "preview": {...},
    "warnings": []
}
```

The LLM context should receive a compact version. Full internal parser details can be saved to disk for debugging.

### 3.5 Storage

Store cached introspection next to uploaded metadata:

```text
static/uploads/file_.../
  original.txt
  metadata.json
  introspection.v1.json
```

Also allow global cache by sha256:

```text
static/file_introspection_cache/{sha256}.v1.json
```

The per-file cache is simple; the sha256 cache prevents repeated parsing of duplicate uploads.

## 4. Tool Design

### 4.1 Add `inspect_uploaded_file`

Add a new OpenAI tool:

```json
{
  "name": "inspect_uploaded_file",
  "description": "Inspect an uploaded or system-generated materials file and return a structured content summary for tool selection.",
  "parameters": {
    "type": "object",
    "properties": {
      "file_id": {
        "type": "string"
      },
      "detail_level": {
        "type": "string",
        "enum": ["default", "fuller"]
      }
    },
    "required": ["file_id"],
    "additionalProperties": false
  }
}
```

Execution:

1. Validate `file_id`.
2. Load metadata.
3. Resolve path through `upload_store`.
4. Run or load file introspection.
5. Return a sanitized summary, not raw full file content by default.

### 4.2 Keep `render_with_mcp`

`render_with_mcp` remains the only LLM-facing visualization tool.

The backend continues to route:

```text
intent + input_type + file metadata -> server/tool whitelist
```

The LLM must never choose:

- MCP server name
- remote MCP tool name
- local file path
- API key
- base64 content

### 4.3 Keep `get_mp_structure`

`get_mp_structure` remains LLM-callable.

Upgrade the prompt and tests so that:

- If no file is uploaded and the user asks about a specific material structure, the LLM may call `get_mp_structure`.
- If the user asks for visualization, the LLM should use the returned/generated `file_id` in a later `render_with_mcp` call.
- If the user asks for search or screening, the LLM should use `search_materials_by_criteria`.

## 5. Workflow Changes

### 5.1 Request Setup

Current:

```text
load metadata -> send metadata to LLM
```

Upgrade:

```text
load metadata
run or load compact file introspection
send compact file context to LLM
```

The first LLM call should already know enough for most uploads.

### 5.2 Prompt Policy

Update the system prompt with these rules:

- Uploaded file content summaries are authoritative for tool selection.
- If file summary confidence is high, call `render_with_mcp` directly.
- If summary is ambiguous, call `inspect_uploaded_file` or ask the user to clarify.
- If no file is uploaded and a specific material is requested, call `get_mp_structure` when structure/CIF/crystal/visualization is needed.
- If `get_mp_structure` returns `generated_file_id`, use that id for downstream structure visualization.
- Never invent file ids, material facts, MCP routes, or CIF content.

### 5.3 Context Update After Tools

After `inspect_uploaded_file`:

- Append the returned summary to the message history.
- Optionally update `ctx.uploaded_files[index]["introspection"]`.

After `get_mp_structure`:

- Keep existing `ctx.structure_result`.
- Register generated CIF as a system file.
- Append generated file metadata and compact introspection to the context.

After `render_with_mcp`:

- Append artifact to `ctx.artifacts`.

## 6. Speed Optimization Plan

### 6.1 Parallelize Independent Tool Calls

Current workflow executes tool calls serially:

```text
tool_call_1 -> tool_call_2 -> tool_call_3
```

Upgrade to:

```text
parallel execute safe independent tool calls
```

Safe parallel candidates:

- Multiple `render_with_mcp` calls for different files.
- Multiple `inspect_uploaded_file` calls.
- `search_materials_by_criteria` and unrelated file inspection.

Keep serial when:

- A later call depends on `generated_file_id` from `get_mp_structure`.
- A render call depends on a prior inspection result.

Implementation:

- Add a small executor in `WorkflowOrchestrator`, for example `ThreadPoolExecutor(max_workers=4)`.
- Preserve tool result order when appending tool messages.
- Emit step events as each tool completes.
- Add per-tool timeout handling.

### 6.2 Avoid Unnecessary Second LLM Call

Current behavior may call the LLM once for tool selection and again for final answer composition.

Optimization:

- For artifact-only results, use a deterministic answer template.
- For structure results, use a deterministic answer when the returned facts are complete.
- Only call `_final_answer_from_context()` when the user asked for explanatory analysis that needs synthesis.

Suggested policy:

```text
If ctx.artifacts exists and no complex explanatory request:
  template answer
Else if get_mp_structure returned formula/mp_id/spacegroup:
  template answer plus key facts
Else:
  final LLM composition
```

This can remove one LLM round from common visualization flows.

### 6.3 One-Shot Tool Planning

Keep LLM tool control, but reduce tool rounds.

Prompt the first LLM call to produce all independent tool calls in one response:

Examples:

- User uploads DOS and XRD files and asks to visualize both.
- LLM should issue two `render_with_mcp` calls in the same assistant response.

This pairs well with parallel execution.

### 6.4 Precompute File Introspection

On upload:

- Save file immediately.
- For small files, run introspection synchronously before returning upload response.
- For larger files, return upload response quickly and lazy-compute introspection during chat.

Recommended first implementation:

- Lazy introspection in chat request path.
- Cache by sha256.
- Add upload-time precompute later if chat latency is still too high.

### 6.5 Cache Expensive Results

Add caches:

#### File Introspection Cache

Key:

```text
sha256 + parser_version
```

#### MP Structure Cache

Current code already checks local CIF files before MP API. Improve it by caching:

```text
identifier -> structure result + generated_file_id
```

This avoids repeatedly registering the same CIF and repeated MP calls.

#### MCP Artifact Cache

Optional but useful.

Key:

```text
file_sha256 + intent + route_version + server_name + tool_name
```

Value:

```json
{
  "render_url": "...",
  "expires_at": 1234567890
}
```

Only reuse if `expires_at` is safely in the future.

### 6.6 HTTP Connection Reuse

If `mcp_gateway` currently creates new HTTP clients per call, switch to a reusable client/session.

Requirements:

- Keep timeouts explicit.
- Do not reuse broken sessions forever.
- Add retry only for safe transient errors.

### 6.7 Tune MP API Waiting

Current local throttle is 3 seconds. Keep safety, but improve perceived speed:

- Prefer local CIF cache before waiting.
- Cache identifier misses briefly.
- Do not call MP API if the user did not ask for material-specific structure/search.
- If MP is blocked, fail fast with circuit breaker message.

Do not remove rate limiting blindly; MP blocking would make the system slower and less reliable.

### 6.8 Stream Earlier Progress

Improve perceived latency through SSE:

- Emit `file_introspection` step start/end.
- Emit `tool_plan` step after LLM decides tools.
- Emit individual tool completion events as parallel tools finish.
- Return partial artifact events in the future, before final answer, if frontend supports it.

First version can keep final artifacts in the final event.

## 7. Implementation Phases

### Phase 1: File Understanding Foundation

Files:

- `core/file_introspection.py`
- `core/upload_store.py`
- `core/workflow.py`
- `core/workflow_types.py`
- `core/tools.py`
- tests

Tasks:

1. Add file introspection module.
2. Add parsers for `.cif`, `.txt`, `.dat`, `.csv`, `.xlsx`.
3. Cache introspection by sha256/parser version.
4. Put compact summaries into the initial LLM context.
5. Add `inspect_uploaded_file` tool.
6. Add tests for parser output and workflow context injection.

Acceptance:

- LLM context contains content summaries, not only metadata.
- Small DOS/XRD examples get correct recommended intents.
- Ambiguous text files are marked as ambiguous.

### Phase 2: LLM Tool Policy Upgrade

Files:

- `core/workflow.py`
- `core/tools.py`
- tests

Tasks:

1. Update system prompt rules.
2. Ensure `get_mp_structure` remains LLM-callable when no file is uploaded.
3. Ensure generated CIF file ids are shown to the LLM.
4. Let the LLM chain `get_mp_structure -> render_with_mcp`.
5. Add tests with mocked LLM tool calls.

Acceptance:

- Query: `Show and visualize the crystal structure of LiFePO4`
  - Calls `get_mp_structure`.
  - Registers generated CIF.
  - Calls `render_with_mcp(intent="structure")`.
- Query with uploaded DOS file:
  - Uses file summary.
  - Calls `render_with_mcp(intent="dos")`.

### Phase 3: Workflow Speed Pass

Files:

- `core/workflow.py`
- `core/mcp_gateway.py`
- tests

Tasks:

1. Execute independent tool calls in parallel.
2. Add deterministic final-answer fast paths.
3. Add per-tool timeout handling.
4. Reuse HTTP sessions for MCP calls if applicable.
5. Add latency measurements in step data.

Acceptance:

- Two independent MCP renders run concurrently.
- Common artifact-only flow uses one LLM call instead of two.
- Existing tests still pass.

### Phase 4: Frontend Observability

Files:

- `frontend/src/components/TracePanel.tsx`
- `frontend/src/components/VisualizationPanel.tsx`
- `frontend/src/types.ts`

Tasks:

1. Show file introspection step in the trace.
2. Show MCP render steps as they finish.
3. Optionally support incremental artifact events before final.

Acceptance:

- User can see whether the system is inspecting files, calling MP API, or rendering MCP.

## 8. Test Plan

Use the project Conda environment for Python:

```powershell
conda run -n agno-assist pytest ...
conda run -n agno-assist python ...
```

### Unit Tests

Add:

```text
tests/test_file_introspection.py
tests/test_workflow_file_understanding.py
tests/test_workflow_parallel_tools.py
```

Cover:

- CIF summary extraction.
- DOS-like text summary.
- XRD-like text summary.
- Ambiguous `.dat` summary.
- CSV summary.
- XLSX summary.
- `inspect_uploaded_file` tool result.
- Uploaded file context contains summaries.
- No-upload material query can call MP structure tool.
- Generated CIF can be used by `render_with_mcp`.
- Parallel render calls preserve correct tool-call responses.

### Integration Tests

Use mocked MCP gateway and mocked LLM responses.

Scenarios:

1. Upload DOS file -> LLM calls `render_with_mcp(dos)`.
2. Upload XRD file -> LLM calls `render_with_mcp(xrd)`.
3. Upload XLSX binary phase file -> LLM calls `render_with_mcp(binary_phase)`.
4. No upload, ask LiFePO4 structure visualization -> MP structure then MCP structure.
5. Ambiguous text file -> inspect tool or clarification, not random MCP route.

### Performance Tests

Track:

- Time from chat request to first `step_start`.
- Time to file introspection.
- Time to first LLM response.
- Tool execution time per tool.
- Final answer composition time.
- Total request time.

Compare before/after:

- Single uploaded DOS render.
- Two uploaded files rendered independently.
- MP structure query with cached CIF.
- MP structure query requiring remote MP API.

## 9. Risk Controls

### Token Risk

Do not put full large files into the LLM context.

Recommended limits:

- Small text full preview: under 16 KB.
- Default preview: first 40 lines plus detected table profile.
- Large text: sampled rows and stats only.
- XLSX: sheet summaries and first rows only.

### Safety Risk

Keep all file path resolution in `upload_store`.

Never expose:

- local absolute file paths
- base64 content
- server API keys
- MCP server headers

### Tool Misrouting Risk

LLM can recommend intent, but backend route validation remains mandatory:

- allowed intent
- allowed extension
- valid file id
- whitelisted server/tool

### Latency Risk

Parallelism must be bounded:

```text
max_parallel_tool_calls = 4
max_parallel_mcp_renders = 3
per_tool_timeout_sec = 60
```

Do not let one slow MCP render block all other completed results internally.

## 10. Recommended First PR Scope

Keep the first implementation focused:

1. Add `core/file_introspection.py`.
2. Support `.cif`, `.txt`, `.dat`, `.csv`, `.xlsx`.
3. Inject compact file summaries into LLM context.
4. Add `inspect_uploaded_file`.
5. Update prompt rules for uploaded files and no-upload MP API calls.
6. Add tests for introspection and LLM context.

Do the speed pass in the next PR unless the first implementation stays small. The speed pass touches workflow execution order and should be reviewed separately.

## 11. Success Definition

The upgrade is successful when these are true:

- The LLM sees meaningful file content summaries before choosing tools.
- Uploaded DOS/XRD/phase/structure files are routed based on content, not only filename.
- If no file is uploaded, the LLM can decide to call MP API tools to retrieve CIF/structure.
- Generated CIF files can flow into MCP visualization tools.
- Common visualization flows require fewer LLM calls.
- Multiple independent MCP renders can run in parallel.
- The frontend receives the same final `artifacts` shape and does not need to know MCP route internals.
