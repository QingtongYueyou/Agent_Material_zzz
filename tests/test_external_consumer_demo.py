from __future__ import annotations

from unittest.mock import patch

from fastapi.testclient import TestClient

from demo.external_consumer.app import app


client = TestClient(app)


def test_demo_proxies_capability_catalog() -> None:
    payload = {"capabilities": [{"intent": "structure"}, {"intent": "3dgs"}]}
    with patch("demo.external_consumer.app._upstream_json", return_value=payload) as upstream:
        response = client.get("/api/capabilities")

    assert response.status_code == 200
    assert response.json() == payload
    upstream.assert_called_once_with("GET", "/api/visualizations/capabilities")


def test_demo_forwards_visualization_request_without_using_project_modules() -> None:
    request = {"intent": "3dgs", "input_type": "asset", "filename": "object.ply"}
    result = {"ok": True, "render_url": "http://viewer.test/session"}
    with patch("demo.external_consumer.app._upstream_json", return_value=result) as upstream:
        response = client.post("/api/visualizations/render", json=request)

    assert response.status_code == 200
    assert response.json() == result
    upstream.assert_called_once_with("POST", "/api/visualizations/render", json=request)


def test_demo_forwards_natural_language_chat_request() -> None:
    request = {"query": "自动选择 MCP 可视化 LiFePO4", "file_ids": []}
    result = {"events": [], "final": {"answer": "done", "artifacts": []}}
    with patch("demo.external_consumer.app._upstream_json", return_value=result) as upstream:
        response = client.post("/api/chat", json=request)

    assert response.status_code == 200
    assert response.json() == result
    upstream.assert_called_once_with("POST", "/api/chat", json=request)


def test_demo_forwards_uploaded_file() -> None:
    result = {"file_id": "file-1", "filename": "sample.cif"}
    with patch("demo.external_consumer.app._upstream_json", return_value=result) as upstream:
        response = client.post(
            "/api/files/upload",
            files={"file": ("sample.cif", b"data_test", "chemical/x-cif")},
        )

    assert response.status_code == 200
    assert response.json() == result
    call = upstream.call_args
    assert call.args == ("POST", "/api/files/upload")
    assert call.kwargs["files"]["file"] == ("sample.cif", b"data_test", "chemical/x-cif")
