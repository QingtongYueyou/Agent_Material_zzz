from __future__ import annotations

import json
import re
import uuid
from textwrap import dedent
from typing import Any

from core.llm_client import LLMClientError, create_chat_completion
from core.planner_schema import (
    allowed_tool_contract,
    base_response,
    clean_tool_calls,
    normalize_available_tools,
)


SYSTEM_PROMPT = dedent(
    """
    You are server B in a two-server materials visualization system.

    Your only job is to convert the user's natural-language request into a strict JSON tool-call plan for server A.
    Server A will execute database lookup, file retrieval, WebSocket push, visualization, and final answer generation.

    Hard rules:
    - Output JSON only. Do not use Markdown.
    - Do not write a final natural-language answer for the user.
    - Do not claim that files were found, loaded, rendered, or analyzed.
    - Use only tools listed in available_tools.
    - If the request is ambiguous and cannot be executed safely, set clarification_needed to true.
    - Prefer explicit mp-id over formula when both are present.
    - For structure, CIF, crystal, lattice, composition, XRD, or 3D visualization requests, include material.get_structure_file before visualization tools.
    - For filtering/search requests, use material.search.

    Required JSON shape:
    {
      "intent": "string",
      "confidence": 0.0,
      "clarification_needed": false,
      "clarification_question": null,
      "tool_calls": [
        {
          "tool": "tool.name",
          "arguments": {}
        }
      ]
    }
    """
).strip()


_MP_ID_RE = re.compile(r"\bmp-\d+\b", re.IGNORECASE)
_FORMULA_RE = re.compile(r"\b(?:[A-Z][a-z]?\d*){2,}\b")
_ELEMENT_RE = re.compile(r"\b[A-Z][a-z]?\b")
_BAND_GAP_MIN_RE = re.compile(r"(?:带隙|band\s*gap)[^\d]*(?:大于|高于|超过|>=|>|不少于)?\s*(\d+(?:\.\d+)?)\s*(?:eV)?", re.IGNORECASE)


def _extract_json_object(text: str) -> dict[str, Any] | None:
    text = (text or "").strip()
    if not text:
        return None

    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text)

    try:
        data = json.loads(text)
        return data if isinstance(data, dict) else None
    except Exception:
        pass

    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None

    try:
        data = json.loads(text[start : end + 1])
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def _string_or_none(value: Any) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _material_slots(query: str) -> dict[str, Any]:
    slots: dict[str, Any] = {
        "mp_id": None,
        "formula": None,
        "elements": None,
    }

    mp_match = _MP_ID_RE.search(query)
    if mp_match:
        slots["mp_id"] = mp_match.group(0).lower()

    formula_match = _FORMULA_RE.search(query)
    if formula_match:
        slots["formula"] = formula_match.group(0)

    elements = list(dict.fromkeys(_ELEMENT_RE.findall(query)))
    if elements:
        slots["elements"] = elements[:6]

    return slots


def _extract_band_gap_min(query: str) -> float | None:
    match = _BAND_GAP_MIN_RE.search(query)
    if not match:
        return None
    try:
        return float(match.group(1))
    except Exception:
        return None


def _fallback_plan(
    *,
    query: str,
    trace_id: str,
    available_tools: list[str],
    reason: str,
) -> dict[str, Any]:
    slots = _material_slots(query)
    q_lower = query.lower()
    tool_calls: list[dict[str, Any]] = []

    wants_search = any(keyword in query for keyword in ("搜索", "筛选", "查找", "找", "候选", "稳定", "带隙"))
    wants_search = wants_search or any(keyword in q_lower for keyword in ("search", "find", "filter", "candidate"))

    wants_xrd = "xrd" in q_lower or "衍射" in query or "图谱" in query
    wants_3d = any(keyword in query for keyword in ("3D", "三维", "可视化", "结构", "晶体", "晶胞"))
    wants_composition = "组分" in query or "composition" in q_lower
    wants_lattice = "晶格" in query or "晶胞" in query or "lattice" in q_lower

    has_material_identifier = bool(slots.get("mp_id") or slots.get("formula"))

    if wants_search and "material.search" in available_tools:
        band_gap_min = _extract_band_gap_min(query)
        if band_gap_min is None and "绝缘" in query:
            band_gap_min = 2.0

        args: dict[str, Any] = {
            "elements": slots.get("elements"),
            "formula": slots.get("formula"),
            "mp_id": slots.get("mp_id"),
            "band_gap_min": band_gap_min,
            "band_gap_max": None,
            "is_stable": True if "稳定" in query else None,
            "crystal_system": None,
            "limit": 5,
        }
        tool_calls.append({"tool": "material.search", "arguments": args})

    if has_material_identifier and (wants_3d or wants_xrd or wants_lattice or wants_composition):
        if "material.get_structure_file" in available_tools:
            tool_calls.append(
                {
                    "tool": "material.get_structure_file",
                    "arguments": {
                        "formula": slots.get("formula"),
                        "mp_id": slots.get("mp_id"),
                        "file_type": "cif",
                    },
                }
            )
        if wants_3d and "visualization.render_3dgs" in available_tools:
            tool_calls.append(
                {
                    "tool": "visualization.render_3dgs",
                    "arguments": {
                        "formula": slots.get("formula"),
                        "mp_id": slots.get("mp_id"),
                        "preferred_model": None,
                    },
                }
            )
        if (wants_lattice or wants_3d) and "visualization.render_lattice" in available_tools:
            tool_calls.append({"tool": "visualization.render_lattice", "arguments": {}})
        if (wants_composition or wants_3d) and "visualization.render_composition" in available_tools:
            tool_calls.append({"tool": "visualization.render_composition", "arguments": {}})
        if wants_xrd and "visualization.render_xrd" in available_tools:
            tool_calls.append({"tool": "visualization.render_xrd", "arguments": {"wavelength": "CuKa"}})

    cleaned_calls = clean_tool_calls(tool_calls, available_tools)
    if cleaned_calls:
        intent = "material_search" if wants_search and not has_material_identifier else "structure_visualization"
        return base_response(
            trace_id=trace_id,
            intent=intent,
            confidence=0.55,
            tool_calls=cleaned_calls,
            available_tools=available_tools,
            source=f"fallback:{reason}",
        )

    return base_response(
        trace_id=trace_id,
        intent="clarification",
        confidence=0.3,
        tool_calls=[],
        available_tools=available_tools,
        clarification_needed=True,
        clarification_question="请提供明确的材料化学式、MP-ID，或需要执行的搜索/可视化条件。",
        source=f"fallback:{reason}",
    )


def _build_user_prompt(query: str, context: dict[str, Any], available_tools: list[str]) -> str:
    payload = {
        "query": query,
        "context": context,
        "available_tools": available_tools,
        "tool_contract": allowed_tool_contract(available_tools),
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def _normalize_llm_plan(data: dict[str, Any], trace_id: str, available_tools: list[str]) -> dict[str, Any] | None:
    tool_calls = clean_tool_calls(data.get("tool_calls"), available_tools)
    clarification_needed = bool(data.get("clarification_needed", False))
    clarification_question = _string_or_none(data.get("clarification_question"))

    if not tool_calls and not clarification_needed:
        return None

    try:
        confidence = float(data.get("confidence", 0.0))
    except Exception:
        confidence = 0.0

    intent = _string_or_none(data.get("intent")) or "unknown"

    return base_response(
        trace_id=trace_id,
        intent=intent,
        confidence=confidence,
        tool_calls=tool_calls,
        available_tools=available_tools,
        clarification_needed=clarification_needed,
        clarification_question=clarification_question,
        source="llm",
    )


def create_tool_plan(
    query: str,
    *,
    session_id: str | None = None,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    trace_id = str(uuid.uuid4())
    context = dict(context or {})
    if session_id:
        context.setdefault("session_id", session_id)

    available_tools = normalize_available_tools(context.get("available_tools"))
    query = query.strip()
    if not query:
        return base_response(
            trace_id=trace_id,
            intent="clarification",
            confidence=1.0,
            tool_calls=[],
            available_tools=available_tools,
            clarification_needed=True,
            clarification_question="请输入需要分析或可视化的材料问题。",
            source="validation",
        )

    try:
        message = create_chat_completion(
            [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": _build_user_prompt(query, context, available_tools)},
            ],
            temperature=0.0,
            max_tokens=900,
            tool_choice="none",
        )
    except LLMClientError as exc:
        return _fallback_plan(
            query=query,
            trace_id=trace_id,
            available_tools=available_tools,
            reason="llm_error",
        )

    content = message.get("content")
    if not isinstance(content, str):
        return _fallback_plan(
            query=query,
            trace_id=trace_id,
            available_tools=available_tools,
            reason="non_text_llm_content",
        )

    data = _extract_json_object(content)
    if data is None:
        return _fallback_plan(
            query=query,
            trace_id=trace_id,
            available_tools=available_tools,
            reason="invalid_json",
        )

    normalized = _normalize_llm_plan(data, trace_id, available_tools)
    if normalized is None:
        return _fallback_plan(
            query=query,
            trace_id=trace_id,
            available_tools=available_tools,
            reason="invalid_tool_calls",
        )

    return normalized
