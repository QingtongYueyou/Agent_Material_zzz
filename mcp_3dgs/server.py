from __future__ import annotations

import json
import re
from html import escape
from pathlib import Path
from typing import Any
from urllib.parse import quote

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from mcp_3dgs import rendering


app = FastAPI(title="Agent Material 3DGS MCP", version="0.1.0")
create_render = rendering.create_render

VIEWER_DIR = Path(__file__).resolve().parent / "viewer"
VIEWER_DIST_DIR = VIEWER_DIR / "dist"
VIEWER_INDEX_HTML = VIEWER_DIST_DIR / "index.html"
VIEWER_ASSETS_DIR = VIEWER_DIST_DIR / "assets"

app.mount(
    "/viewer/assets",
    StaticFiles(directory=VIEWER_ASSETS_DIR, check_dir=False),
    name="viewer-assets",
)


def _json_rpc_success(request_id: Any, result: Any) -> JSONResponse:
    return JSONResponse({"jsonrpc": "2.0", "id": request_id, "result": result})


def _json_rpc_error(request_id: Any, code: int, message: str) -> JSONResponse:
    return JSONResponse(
        {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}},
        status_code=200,
    )


def _tool_spec() -> dict[str, Any]:
    return {
        "name": "3dgs.create_render",
        "description": "Create a temporary 3DGS viewer session for a resolved splat asset.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "filename": {"type": "string"},
                "quality": {"type": "string", "default": rendering.DEFAULT_QUALITY},
                "ttl_sec": {"type": "integer"},
            },
            "required": ["filename"],
        },
    }


@app.post("/mcp")
async def mcp_endpoint(request: Request) -> JSONResponse:
    try:
        payload = await request.json()
    except json.JSONDecodeError:
        return _json_rpc_error(None, -32700, "Invalid JSON-RPC payload.")

    if not isinstance(payload, dict):
        return _json_rpc_error(None, -32600, "JSON-RPC payload must be an object.")

    request_id = payload.get("id")
    method = payload.get("method")
    params = payload.get("params") if isinstance(payload.get("params"), dict) else {}

    if method == "initialize":
        return _json_rpc_success(
            request_id,
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "agent-material-3dgs", "version": "0.1.0"},
            },
        )

    if method == "tools/list":
        return _json_rpc_success(request_id, {"tools": [_tool_spec()]})

    if method != "tools/call":
        return _json_rpc_error(request_id, -32601, f"Unsupported method: {method}")

    if params.get("name") != "3dgs.create_render":
        return _json_rpc_error(request_id, -32602, "Unsupported tool name.")

    arguments = params.get("arguments")
    if not isinstance(arguments, dict):
        return _json_rpc_error(request_id, -32602, "Tool arguments must be an object.")

    try:
        result = rendering.create_render(
            str(arguments.get("filename") or ""),
            quality=str(arguments.get("quality") or rendering.DEFAULT_QUALITY),
            ttl_sec=arguments.get("ttl_sec"),
        )
    except (rendering.RenderCreateError, TypeError, ValueError) as exc:
        return _json_rpc_error(request_id, -32602, str(exc))

    return _json_rpc_success(request_id, result)


@app.get("/health")
def health() -> dict[str, Any]:
    rendering.prune_expired_sessions()
    return {
        "ok": True,
        "service": "agent-material-3dgs-mcp",
        "sessions": len(rendering.sessions),
        "public_base_url": rendering._public_base_url(),
    }


def _session_config_script(session_id: str) -> str:
    config_url = f"/viewer/sessions/{quote(session_id, safe='')}/config"
    payload = json.dumps(config_url).replace("</", "<\\/")
    return f'<script type="application/json" id="session-config-url">{payload}</script>'


def _viewer_unbuilt_html(session_id: str, message: str) -> str:
    safe_session_id = escape(session_id, quote=True)
    safe_message = escape(message, quote=True)
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>3DGS Viewer Not Built</title>
  <style>
    body {{
      margin: 0;
      font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background: #101418;
      color: #f4f7fb;
    }}
    #root {{
      min-height: 100vh;
      display: grid;
      place-items: center;
      padding: 24px;
      box-sizing: border-box;
    }}
    .viewer-build-error {{
      max-width: 720px;
      border: 1px solid #39424e;
      border-radius: 8px;
      padding: 20px;
      background: #18202a;
      line-height: 1.5;
    }}
    code {{
      color: #9bd3ff;
    }}
  </style>
</head>
<body>
  <main id="root" data-session-id="{safe_session_id}">
    <section class="viewer-build-error">
      <h1>3DGS viewer app is not built</h1>
      <p>{safe_message}</p>
      <p>Build the standalone viewer before serving sessions: <code>cd mcp_3dgs/viewer && npm install && npm run build</code>.</p>
    </section>
  </main>
  {_session_config_script(session_id)}
</body>
</html>"""


def _rewrite_viewer_index(index_html: str, session_id: str) -> str:
    safe_session_id = escape(session_id, quote=True)
    html = re.sub(
        r'(?P<prefix>\b(?:src|href)=["\'])(?:/)?assets/',
        r"\g<prefix>/viewer/assets/",
        index_html,
    )

    root_pattern = re.compile(
        r'<(?P<tag>[a-zA-Z][\w:-]*)(?P<attrs>[^>]*)\bid=(?P<quote>["\'])root(?P=quote)(?P<after>[^>]*)>'
        r".*?</(?P=tag)>",
        flags=re.IGNORECASE | re.DOTALL,
    )
    root = f'<main id="root" data-session-id="{safe_session_id}"></main>'
    html, root_count = root_pattern.subn(root, html, count=1)
    if root_count == 0:
        html = re.sub(r"<body([^>]*)>", rf"<body\1>\n  {root}", html, count=1, flags=re.IGNORECASE)

    config_script = _session_config_script(session_id)
    if 'id="session-config-url"' not in html and "id='session-config-url'" not in html:
        html = html.replace(root, f"{root}\n  {config_script}", 1)
    return html


@app.get("/viewer/sessions/{session_id}", response_class=HTMLResponse)
def viewer_session(session_id: str) -> str:
    if not VIEWER_INDEX_HTML.exists():
        return _viewer_unbuilt_html(
            session_id,
            f"Expected Vite build output at {VIEWER_INDEX_HTML}, but index.html was not found.",
        )

    try:
        index_html = VIEWER_INDEX_HTML.read_text(encoding="utf-8")
    except OSError as exc:
        return _viewer_unbuilt_html(session_id, f"Could not read {VIEWER_INDEX_HTML}: {exc}")

    if "/assets/" not in index_html and 'src="assets/' not in index_html and "href=\"assets/" not in index_html:
        return _viewer_unbuilt_html(
            session_id,
            f"{VIEWER_INDEX_HTML} does not reference Vite asset bundles. Rebuild the viewer app.",
        )

    return _rewrite_viewer_index(index_html, session_id)



@app.get("/viewer/sessions/{session_id}/config")
def viewer_session_config(session_id: str) -> dict[str, Any]:
    try:
        return rendering.get_session_config(session_id)
    except rendering.SessionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except rendering.SessionExpiredError as exc:
        raise HTTPException(status_code=410, detail=str(exc)) from exc


@app.get("/assets/{relative_path:path}")
def asset_file(relative_path: str) -> FileResponse:
    try:
        return FileResponse(rendering.resolve_asset_relative_path(relative_path))
    except rendering.AssetPathError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
