from __future__ import annotations

from unittest.mock import patch

from fastapi.testclient import TestClient

from api.main import app


client = TestClient(app)


def test_capabilities_include_3dgs_and_external_mcp_routes() -> None:
    response = client.get("/api/visualizations/capabilities")

    assert response.status_code == 200
    capabilities = {item["intent"]: item for item in response.json()["capabilities"]}
    assert capabilities["3dgs"]["tool"] == "3dgs.create_render"
    assert capabilities["structure"]["provider"] == "fz-mcp-server"
    assert capabilities["dos"]["tool"] == "dos.dos_file"


def test_unified_render_routes_3dgs_without_llm() -> None:
    render_result = {
        "ok": True,
        "session_id": "session-1",
        "render_url": "http://viewer.test/session-1?token=secret",
        "asset": {},
    }
    with patch("api.main.create_3dgs_render", return_value=render_result) as create_render:
        response = client.post(
            "/api/visualizations/render",
            json={
                "intent": "3dgs",
                "input_type": "asset",
                "filename": "object.ply",
                "quality": "balanced",
                "render_profile": "quality",
            },
        )

    assert response.status_code == 200
    assert response.json()["tool"] == "3dgs.create_render"
    assert response.json()["render_url"] == render_result["render_url"]
    create_render.assert_called_once_with("object.ply", quality="balanced", render_profile="quality")


def test_unified_render_routes_external_mcp_without_llm() -> None:
    artifact = {
        "id": "artifact-1",
        "kind": "mcp_visualization",
        "title": "结构可视化",
        "intent": "structure",
        "display": "iframe",
        "render_url": "http://external-viewer.test/structure-1",
        "source_file_id": "file-1",
    }
    with patch("api.main.execute_openai_tool", return_value=artifact) as execute_tool:
        response = client.post(
            "/api/visualizations/render",
            json={"intent": "structure", "input_type": "file", "file_id": "file-1"},
        )

    assert response.status_code == 200
    assert response.json()["provider"] == "fz-mcp-server"
    assert response.json()["tool"] == "fz.mol_file"
    assert response.json()["render_url"] == artifact["render_url"]
    execute_tool.assert_called_once_with(
        "render_with_mcp",
        {"intent": "structure", "input_type": "file", "file_id": "file-1"},
    )


def test_unified_render_validates_input_for_each_provider() -> None:
    missing_filename = client.post(
        "/api/visualizations/render",
        json={"intent": "3dgs", "input_type": "asset"},
    )
    missing_file_id = client.post(
        "/api/visualizations/render",
        json={"intent": "dos", "input_type": "file"},
    )
    unsupported = client.post(
        "/api/visualizations/render",
        json={"intent": "unknown", "input_type": "file", "file_id": "file-1"},
    )

    assert missing_filename.status_code == 400
    assert missing_file_id.status_code == 400
    assert unsupported.status_code == 400
