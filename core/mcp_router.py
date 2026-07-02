from __future__ import annotations

from pathlib import Path
from typing import Any


class MCPRouteError(RuntimeError):
    pass


ROUTE_TABLE: dict[str, dict[str, Any]] = {
    "structure": {
        "title": "结构可视化",
        "server_name": "fz-mcp-server",
        "file_tool": "fz.mol_file",
        "url_tool": "fz.mol_url",
        "extensions": {".cif", ".xyz", ".poscar", ".cell", ".pdb"},
    },
    "dos": {
        "title": "DOS 可视化",
        "server_name": "dos-mcp-server",
        "file_tool": "dos.dos_file",
        "url_tool": "dos.dos_url",
        "extensions": {".dat", ".txt"},
    },
    "xrd": {
        "title": "XRD 可视化",
        "server_name": "x-ray-mcp-server",
        "file_tool": "x_ray.xrd_file",
        "url_tool": "x_ray.xrd_url",
        "extensions": {".dat", ".txt"},
    },
    "binary_phase": {
        "title": "二元相图可视化",
        "server_name": "hot2-mcp-server",
        "file_tool": "hot2.binary_xlsx_file",
        "url_tool": "hot2.binary_xlsx_url",
        "extensions": {".xls", ".xlsx"},
    },
    "ternary_phase": {
        "title": "三元相图可视化",
        "server_name": "hot3-mcp-server",
        "file_tool": "hot3.ternary_xlsx_file",
        "url_tool": "hot3.ternary_xlsx_url",
        "extensions": {".xls", ".xlsx"},
    },
    "band": {
        "title": "Band structure visualization",
        "server_name": "nb-mcp-server",
        "file_tool": "nb.band_zip_file",
        "url_tool": "nb.band_zip_url",
        "extensions": {".zip"},
    },
    "vtp": {
        "title": "VTP model visualization",
        "server_name": "yxy-mcp-server",
        "file_tool": "yxy.vtp_file",
        "url_tool": "yxy.vtp_url",
        "extensions": {".vtp"},
    },
    "model": {
        "title": "3D model visualization",
        "server_name": "hj-ol-mcp-server",
        "file_tool": "hj_ol.model_file",
        "url_tool": "hj_ol.model_url",
        "extensions": {".stl", ".glb"},
    },
    "molecular_dynamics": {
        "title": "Molecular dynamics visualization",
        "server_name": "fzdl-mcp-server",
        "file_tool": "fzdl.model_file",
        "url_tool": "fzdl.model_url",
        "extensions": {".dump", ".cfg", ".data", ".dat", ".lmp", ".xyz"},
    },
    "phase_curve": {
        "title": "Phase curve visualization",
        "server_name": "xt-mcp-server",
        "file_tool": "xt.phase_curve_file",
        "url_tool": "xt.phase_curve_url",
        "extensions": {".dat", ".txt"},
    },
    "liquidus": {
        "title": "Liquidus projection visualization",
        "server_name": "yxty3-mcp-server",
        "file_tool": "yxty3.liquidus_xlsx_file",
        "url_tool": "yxty3.liquidus_xlsx_url",
        "extensions": {".xls", ".xlsx"},
    },
    "liquidus_dual": {
        "title": "Liquidus dual projection visualization",
        "server_name": "yxty3-mcp-server",
        "file_tool": "yxty3.liquidus_xlsx_file_dual",
        "url_tool": "yxty3.liquidus_xlsx_url_dual",
        "extensions": {".xls", ".xlsx"},
    },
    "liquidus_mass": {
        "title": "Liquidus mass projection visualization",
        "server_name": "yxty3-mcp-server",
        "file_tool": "yxty3.liquidus_xlsx_file_mass",
        "url_tool": "yxty3.liquidus_xlsx_url_mass",
        "extensions": {".xls", ".xlsx"},
    },
    "isothermal": {
        "title": "Isothermal section visualization",
        "server_name": "dw3-mcp-server",
        "file_tool": "dw3.isothermal_xlsx_file",
        "url_tool": "dw3.isothermal_xlsx_url",
        "extensions": {".xls", ".xlsx"},
    },
    "isothermal_dual": {
        "title": "Isothermal dual section visualization",
        "server_name": "dw3-mcp-server",
        "file_tool": "dw3.isothermal_xlsx_file_dual",
        "url_tool": "dw3.isothermal_xlsx_url_dual",
        "extensions": {".xls", ".xlsx"},
    },
    "isothermal_mass": {
        "title": "Isothermal mass section visualization",
        "server_name": "dw3-mcp-server",
        "file_tool": "dw3.isothermal_xlsx_file_mass",
        "url_tool": "dw3.isothermal_xlsx_url_mass",
        "extensions": {".xls", ".xlsx"},
    },
    "vertical_section": {
        "title": "Vertical section visualization",
        "server_name": "cz3-mcp-server",
        "file_tool": "cz3.vertical_xlsx_file",
        "url_tool": "cz3.vertical_xlsx_url",
        "extensions": {".xls", ".xlsx"},
    },
}


def _metadata_extension(metadata: dict[str, Any]) -> str:
    extension = metadata.get("extension")
    if isinstance(extension, str) and extension.strip():
        return extension.strip().lower()

    for key in ("filename", "original_filename", "stored_filename"):
        value = metadata.get(key)
        if isinstance(value, str) and value.strip():
            suffix = Path(value).suffix.lower()
            if suffix:
                return suffix

    raise MCPRouteError("File metadata is missing an extension.")


def resolve_route(intent: str, input_type: str, metadata: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(intent, str) or not intent.strip():
        raise MCPRouteError("intent is required.")
    if not isinstance(input_type, str) or not input_type.strip():
        raise MCPRouteError("input_type is required.")
    if not isinstance(metadata, dict):
        raise MCPRouteError("metadata must be a dict.")

    normalized_intent = intent.strip().lower()
    route = ROUTE_TABLE.get(normalized_intent)
    if route is None:
        allowed = ", ".join(sorted(ROUTE_TABLE))
        raise MCPRouteError(f"Unsupported MCP intent {intent!r}. Allowed intents: {allowed}.")

    normalized_input_type = input_type.strip().lower()
    if normalized_input_type != "file":
        raise MCPRouteError("Only input_type='file' is supported in this version.")

    file_id = metadata.get("file_id")
    if not isinstance(file_id, str) or not file_id.strip():
        raise MCPRouteError("metadata.file_id is required for file input.")

    extension = _metadata_extension(metadata)
    allowed_extensions = {str(item).lower() for item in route["extensions"]}
    if extension not in allowed_extensions:
        allowed = ", ".join(sorted(allowed_extensions))
        raise MCPRouteError(
            f"Intent {normalized_intent!r} does not accept extension {extension!r}. "
            f"Allowed extensions: {allowed}."
        )

    return {
        "intent": normalized_intent,
        "title": route["title"],
        "input_type": normalized_input_type,
        "server_name": route["server_name"],
        "tool_name": route["file_tool"],
        "file_tool": route["file_tool"],
        "url_tool": route["url_tool"],
        "extensions": sorted(allowed_extensions),
        "file_id": file_id,
    }
