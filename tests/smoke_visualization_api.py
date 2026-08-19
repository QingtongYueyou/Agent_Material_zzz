from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from typing import Any


def request_json(
    url: str,
    *,
    method: str = "GET",
    payload: dict[str, Any] | None = None,
    timeout: float,
) -> dict[str, Any]:
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={"Accept": "application/json", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"{method} {url} returned HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Could not connect to {url}: {exc.reason}") from exc

    try:
        result = json.loads(body)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"{method} {url} did not return JSON: {body[:200]}") from exc
    if not isinstance(result, dict):
        raise RuntimeError(f"{method} {url} returned a non-object JSON response.")
    return result


def check_viewer(url: str, timeout: float) -> None:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            content_type = response.headers.get("Content-Type", "")
            body = response.read(512).decode("utf-8", errors="replace").lower()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Viewer returned HTTP {exc.code}: {detail[:200]}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Could not open render_url: {exc.reason}") from exc

    if "text/html" not in content_type.lower() or "<!doctype html" not in body:
        raise RuntimeError(f"render_url did not return an HTML page (Content-Type: {content_type}).")


def redact_url(url: str) -> str:
    return url.split("?", 1)[0] + ("?token=***" if "?" in url else "")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Smoke-test the local Agent Material visualization API.")
    parser.add_argument("--api-base", default="http://127.0.0.1:8080")
    parser.add_argument("--mcp-base", default="http://127.0.0.1:8090")
    parser.add_argument("--filename", default="object.ply")
    parser.add_argument(
        "--quality",
        choices=("auto", "preview", "balanced", "full", "source"),
        default="auto",
    )
    parser.add_argument(
        "--render-profile",
        choices=("performance", "quality"),
        default="performance",
    )
    parser.add_argument("--timeout", type=float, default=15.0)
    parser.add_argument("--skip-viewer", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    api_base = args.api_base.rstrip("/")
    mcp_base = args.mcp_base.rstrip("/")

    try:
        api_health = request_json(f"{api_base}/health", timeout=args.timeout)
        if api_health.get("ok") is not True:
            raise RuntimeError(f"Main API health check failed: {api_health}")
        print("[PASS] Main API health")

        mcp_health = request_json(f"{mcp_base}/health", timeout=args.timeout)
        if mcp_health.get("ok") is not True:
            raise RuntimeError(f"3DGS MCP health check failed: {mcp_health}")
        print("[PASS] 3DGS MCP health")

        result = request_json(
            f"{api_base}/api/3dgs/render",
            method="POST",
            payload={
                "filename": args.filename,
                "quality": args.quality,
                "render_profile": args.render_profile,
            },
            timeout=args.timeout,
        )
        render_url = result.get("render_url")
        if result.get("ok") is not True or not isinstance(render_url, str) or not render_url:
            raise RuntimeError(f"Render response is missing ok/render_url: {result}")
        print(f"[PASS] Render session created: {result.get('session_id', '<unknown>')}")
        print(f"       URL: {redact_url(render_url)}")

        if not args.skip_viewer:
            check_viewer(render_url, args.timeout)
            print("[PASS] Viewer HTML is reachable")

    except RuntimeError as exc:
        print(f"[FAIL] {exc}", file=sys.stderr)
        return 1

    print("Visualization API smoke test completed successfully.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
