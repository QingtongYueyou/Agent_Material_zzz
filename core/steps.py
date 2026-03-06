from __future__ import annotations

import json
import re
import time

from core.answer_generator import classify_intent_with_llm, generate_answer_with_llm
from core.processor import get_cif_info
from core.tools import get_mp_structure_raw, search_materials_by_criteria_raw
from core.workflow_types import ErrorCode, StepResult, StepStatus, WorkflowContext


_MP_ID_RE = re.compile(r"\bmp-\d+\b", re.IGNORECASE)
_FORMULA_RE = re.compile(r"\b(?:[A-Z][a-z]?\d*){2,}\b")


def _done(name: str, t0: float, data: dict, fallback: bool = False) -> StepResult:
    return StepResult(
        step_name=name,
        status=StepStatus.SUCCESS,
        data=data,
        latency_ms=int((time.time() - t0) * 1000),
        fallback_used=fallback,
    )


def _fail(name: str, t0: float, code: ErrorCode, msg: str, data: dict | None = None) -> StepResult:
    return StepResult(
        step_name=name,
        status=StepStatus.FAILED,
        data=data or {},
        error_code=code.value,
        error_message=msg,
        latency_ms=int((time.time() - t0) * 1000),
    )


def _extract_slots(question: str) -> dict:
    slots: dict[str, object] = {}

    mp_match = _MP_ID_RE.search(question)
    if mp_match:
        slots["mp_id"] = mp_match.group(0).lower()

    formula_match = _FORMULA_RE.search(question)
    if formula_match:
        slots["formula"] = formula_match.group(0)

    if "稳定" in question:
        slots["is_stable"] = True

    if "绝缘" in question:
        slots["band_gap_min"] = 2.0
    elif "半导体" in question:
        slots["band_gap_min"] = 0.0

    elements = re.findall(r"\b[A-Z][a-z]?\b", question)
    if elements:
        slots["elements"] = list(dict.fromkeys(elements))[:5]

    return slots


def _rule_based_intent(question: str, slots: dict) -> str:
    q = question.lower()
    if slots.get("mp_id") or slots.get("formula") or "结构" in q or "晶体" in q:
        return "STRUCTURE_DETAIL"
    if any(k in q for k in ["筛选", "稳定", "带隙", "search", "查找"]):
        return "SEARCH"
    return "HYBRID"


def step_intent_recognition(ctx: WorkflowContext) -> StepResult:
    t0 = time.time()
    base_slots = _extract_slots(ctx.question)
    llm = classify_intent_with_llm(ctx.question)

    fallback_used = False
    if llm and llm.get("confidence", 0.0) >= 0.55:
        intent = llm["intent"]
        llm_slots = llm.get("slots") or {}
        merged_slots = {
            **base_slots,
            **{k: v for k, v in llm_slots.items() if v not in (None, "", [])},
        }
        # User-explicit identifiers must win over LLM-inferred slots.
        if base_slots.get("mp_id"):
            merged_slots["mp_id"] = base_slots["mp_id"]
        if base_slots.get("formula"):
            merged_slots["formula"] = base_slots["formula"]
            # If user explicitly provides formula/mp-id, force structure-detail route.
            intent = "STRUCTURE_DETAIL"
        source = "llm"
    else:
        intent = _rule_based_intent(ctx.question, base_slots)
        merged_slots = base_slots
        source = "rules"
        fallback_used = llm is not None

    ctx.intent = intent
    ctx.slots = merged_slots

    return _done(
        "intent_recognition",
        t0,
        {
            "intent": ctx.intent,
            "slots": ctx.slots,
            "classifier": source,
            "confidence": llm.get("confidence") if llm else None,
        },
        fallback=fallback_used,
    )


def step_retrieval(ctx: WorkflowContext) -> StepResult:
    t0 = time.time()

    # Direct identifiers should bypass retrieval regardless of intent label.
    if ctx.slots.get("mp_id") or ctx.slots.get("formula"):
        return StepResult(step_name="retrieval", status=StepStatus.SKIPPED)

    try:
        raw = search_materials_by_criteria_raw(
            elements=ctx.slots.get("elements"),
            band_gap_min=ctx.slots.get("band_gap_min"),
            band_gap_max=ctx.slots.get("band_gap_max"),
            is_stable=ctx.slots.get("is_stable"),
            crystal_system=ctx.slots.get("crystal_system"),
            max_results=5,
        )

        data = json.loads(raw) if isinstance(raw, str) and raw.strip().startswith("[") else []
        ctx.retrieval_result = {"items": data}

        if not data:
            return _fail("retrieval", t0, ErrorCode.MP_API_EMPTY_RESULT, "未检索到结果")

        if "mp_id" not in ctx.slots:
            first = data[0].get("MP_ID")
            if first:
                ctx.slots["mp_id"] = str(first)

        return _done("retrieval", t0, {"count": len(data), "items": data})
    except Exception as e:
        return _fail("retrieval", t0, ErrorCode.MP_API_TIMEOUT, str(e))


def step_structure_analysis(ctx: WorkflowContext) -> StepResult:
    t0 = time.time()

    identifier = ctx.slots.get("mp_id") or ctx.slots.get("formula")
    if not identifier:
        items = ctx.retrieval_result.get("items", [])
        if items:
            identifier = str(items[0].get("MP_ID", ""))

    if not identifier:
        return StepResult(step_name="structure_analysis", status=StepStatus.SKIPPED)

    try:
        s = get_mp_structure_raw(str(identifier))
        if isinstance(s, dict) and "error" in s:
            return _fail("structure_analysis", t0, ErrorCode.CIF_PARSE_FAILED, str(s["error"]))

        requested_formula = str(ctx.slots.get("formula") or "").strip().lower()
        returned_formula = str(s.get("formula") or "").strip().lower()
        if requested_formula and returned_formula and requested_formula != returned_formula:
            return _fail(
                "structure_analysis",
                t0,
                ErrorCode.CIF_PARSE_FAILED,
                f"结构结果与请求化学式不一致: requested={requested_formula}, returned={returned_formula}",
            )

        cif_path = s.get("cif_path")
        fname, lat, comp, xrd = get_cif_info(cif_path)
        if not fname:
            return _fail("structure_analysis", t0, ErrorCode.CIF_PARSE_FAILED, "CIF解析失败或无文件")

        ctx.structure_result = s
        ctx.viz_result = {
            "filename": fname,
            "lattice_df": lat,
            "comp_df": comp,
            "xrd_df": xrd,
        }

        return _done(
            "structure_analysis",
            t0,
            {
                "mp_id": s.get("mp_id"),
                "formula": s.get("formula"),
                "crystal_system": s.get("crystal_system"),
                "filename": fname,
            },
        )
    except Exception as e:
        return _fail("structure_analysis", t0, ErrorCode.CIF_PARSE_FAILED, str(e))


def step_visualization_generation(ctx: WorkflowContext) -> StepResult:
    t0 = time.time()
    viz = ctx.viz_result
    if not viz or not viz.get("filename"):
        return _fail("visualization_generation", t0, ErrorCode.VIZ_DATA_MISSING, "无可视化数据")
    return _done("visualization_generation", t0, {"ready": True, "filename": viz.get("filename")})


def _fallback_answer(ctx: WorkflowContext) -> str:
    s = ctx.structure_result
    items = (ctx.retrieval_result or {}).get("items", [])

    if s:
        formula = s.get("formula", "N/A")
        mp_id = s.get("mp_id", "N/A")
        crystal = s.get("crystal_system", "N/A")
        spg = s.get("spacegroup_symbol", "N/A")
        num = s.get("spacegroup_number", "N/A")

        lines = [
            f"已完成 {formula} ({mp_id}) 的结构解析。",
            "",
            f"- 晶系: {crystal}",
            f"- 空间群: {spg} (No.{num})",
            "- 已生成并保存 CIF，可在中间面板查看图表。",
        ]
        return "\n".join(lines)

    if items:
        preview = "\n".join(
            f"- {row.get('MP_ID', 'N/A')} | {row.get('Formula', 'N/A')} | {row.get('Band_Gap', 'N/A')}"
            for row in items[:5]
        )
        return (
            "已完成材料检索，返回候选如下：\n"
            f"{preview}\n\n"
            "如需查看其中某个材料的晶体结构，请告诉我 MP-ID 或化学式。"
        )

    return "已执行工作流，但未拿到可用结构或检索结果，请尝试提供 MP-ID 或化学式。"


def step_answer_composition(ctx: WorkflowContext) -> StepResult:
    t0 = time.time()
    try:
        llm_answer = generate_answer_with_llm(ctx)
        if llm_answer:
            ctx.final_answer = llm_answer
            return _done(
                "answer_composition",
                t0,
                {"answer_len": len(ctx.final_answer), "source": "llm"},
            )

        ctx.final_answer = _fallback_answer(ctx)
        return _done(
            "answer_composition",
            t0,
            {"answer_len": len(ctx.final_answer), "source": "template"},
            fallback=True,
        )
    except Exception as e:
        return _fail("answer_composition", t0, ErrorCode.ANSWER_COMPOSE_FAILED, str(e))
