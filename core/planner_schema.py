from __future__ import annotations

from copy import deepcopy
from typing import Any


DEFAULT_AVAILABLE_TOOLS = [
    "material.search",
    "material.get_structure_file",
    "visualization.render_3dgs",
    "visualization.render_lattice",
    "visualization.render_composition",
    "visualization.render_xrd",
]

VALID_TOOL_ARGUMENT_KEYS: dict[str, set[str]] = {
    "material.search": {
        "elements",
        "formula",
        "mp_id",
        "band_gap_min",
        "band_gap_max",
        "is_stable",
        "crystal_system",
        "limit",
    },
    "material.get_structure_file": {
        "formula",
        "mp_id",
        "file_type",
    },
    "visualization.render_3dgs": {
        "formula",
        "mp_id",
        "preferred_model",
    },
    "visualization.render_lattice": set(),
    "visualization.render_composition": set(),
    "visualization.render_xrd": {
        "wavelength",
    },
}

TOOL_CONTRACT = [
    {
        "tool": "material.search",
        "description": "Search candidate materials by formula, elements, band gap, stability, or crystal system.",
        "arguments": {
            "elements": "array[string] | null",
            "formula": "string | null",
            "mp_id": "string | null",
            "band_gap_min": "number | null",
            "band_gap_max": "number | null",
            "is_stable": "boolean | null",
            "crystal_system": "string | null",
            "limit": "integer",
        },
    },
    {
        "tool": "material.get_structure_file",
        "description": "Ask server A to locate or fetch a CIF structure file for a specific material.",
        "arguments": {
            "formula": "string | null",
            "mp_id": "string | null",
            "file_type": "cif",
        },
    },
    {
        "tool": "visualization.render_3dgs",
        "description": "Ask server A frontend to render a 3D Gaussian Splatting or compatible 3D structure view.",
        "arguments": {
            "formula": "string | null",
            "mp_id": "string | null",
            "preferred_model": "string | null",
        },
    },
    {
        "tool": "visualization.render_lattice",
        "description": "Render lattice parameter panel from the selected structure file.",
        "arguments": {},
    },
    {
        "tool": "visualization.render_composition",
        "description": "Render composition panel from the selected structure file.",
        "arguments": {},
    },
    {
        "tool": "visualization.render_xrd",
        "description": "Render simulated XRD panel from the selected structure file.",
        "arguments": {
            "wavelength": "CuKa",
        },
    },
]


def normalize_available_tools(value: Any) -> list[str]:
    if not isinstance(value, list):
        return list(DEFAULT_AVAILABLE_TOOLS)

    allowed = set(DEFAULT_AVAILABLE_TOOLS)
    normalized = []
    for item in value:
        if not isinstance(item, str):
            continue
        name = item.strip()
        if name in allowed and name not in normalized:
            normalized.append(name)

    return normalized or list(DEFAULT_AVAILABLE_TOOLS)


def allowed_tool_contract(available_tools: list[str]) -> list[dict[str, Any]]:
    available = set(available_tools)
    return [deepcopy(item) for item in TOOL_CONTRACT if item["tool"] in available]


def clean_tool_call(raw: Any, available_tools: list[str]) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None

    tool_name = raw.get("tool")
    if not isinstance(tool_name, str):
        return None
    tool_name = tool_name.strip()
    if tool_name not in available_tools:
        return None

    args = raw.get("arguments")
    if not isinstance(args, dict):
        args = {}

    valid_keys = VALID_TOOL_ARGUMENT_KEYS.get(tool_name, set())
    cleaned_args = {key: value for key, value in args.items() if key in valid_keys}

    if tool_name == "material.search":
        cleaned_args.setdefault("limit", 5)
    elif tool_name == "material.get_structure_file":
        cleaned_args.setdefault("file_type", "cif")
    elif tool_name == "visualization.render_xrd":
        cleaned_args.setdefault("wavelength", "CuKa")

    return {
        "tool": tool_name,
        "arguments": cleaned_args,
    }


def clean_tool_calls(raw_calls: Any, available_tools: list[str]) -> list[dict[str, Any]]:
    if not isinstance(raw_calls, list):
        return []

    cleaned = []
    seen = set()
    for item in raw_calls:
        call = clean_tool_call(item, available_tools)
        if call is None:
            continue
        marker = (call["tool"], repr(sorted(call["arguments"].items())))
        if marker in seen:
            continue
        seen.add(marker)
        cleaned.append(call)

    return cleaned


def base_response(
    *,
    trace_id: str,
    intent: str,
    confidence: float,
    tool_calls: list[dict[str, Any]],
    available_tools: list[str],
    clarification_needed: bool = False,
    clarification_question: str | None = None,
    source: str,
) -> dict[str, Any]:
    return {
        "trace_id": trace_id,
        "intent": intent,
        "confidence": max(0.0, min(1.0, float(confidence))),
        "clarification_needed": clarification_needed,
        "clarification_question": clarification_question,
        "tool_calls": tool_calls,
        "server_a_execution_hint": {
            "requires_database_lookup": any(call["tool"].startswith("material.") for call in tool_calls),
            "requires_websocket_push": any(call["tool"].startswith("visualization.") for call in tool_calls),
            "final_answer_owner": "server_a",
        },
        "planner_meta": {
            "source": source,
            "available_tools": list(available_tools),
        },
    }
