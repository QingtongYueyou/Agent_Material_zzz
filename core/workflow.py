from __future__ import annotations

import json
import re
import time
import uuid
from collections.abc import Generator
from textwrap import dedent
from typing import Any

from core.llm_client import LLMClientError, create_chat_completion
from core.processor import get_cif_info
from core.tools import OPENAI_TOOL_SPECS, execute_openai_tool
from core.workflow_types import ErrorCode, StepResult, StepStatus, WorkflowContext


SYSTEM_PROMPT = dedent(
    """
    你是材料科学助手。默认使用中文回答，面向材料科学研究场景。

    你可以使用两个工具：
    1. `search_materials_by_criteria`：用于模糊检索、筛选候选材料。
    2. `get_mp_structure`：用于按 mp-id 或精确化学式获取具体结构详情。

    工具使用规则：
    - 用户明确给出 mp-id 或精确化学式，并要求结构、晶体、空间群、CIF、配位环境等信息时，优先调用 `get_mp_structure`。
    - 用户是在做筛选、搜索、条件检索时，调用 `search_materials_by_criteria`。
    - 不要伪造 Materials Project 数据；必须基于工具返回结果作答。
    - 如结构工具已经返回具体材料，最终答案中必须明确包含该材料的 formula 和 mp_id。
    - 不要输出原始 CIF 正文，不要输出 ` ```cif ` 代码块，不要逐行转抄工具返回的原始字段。
    - 最终回答必须是整理后的自然语言说明，而不是原始数据转储。
    """
).strip()


FINAL_ANSWER_PROMPT = dedent(
    """
    你现在只负责生成最终用户答案，不再调用任何工具。

    输出格式要求：
    - 默认使用中文。
    - 保持简洁、专业、清晰。
    - 不要输出原始 JSON、原始 CIF 文本、代码块或“CIF 内容如下”之类的话。
    - 如果是结构查询，严格按下面格式组织：

    **概览**
    - 材料名称/化学式：...
    - MP-ID：...
    - 晶系：...
    - 空间群：...

    **结构特征**
    - 用 2 到 4 条要点概括晶胞参数、结构特征或可从现有事实安全推出的信息。
    - 如果当前事实不足以判断配位环境或连接方式，就明确说“当前数据不足以直接判断”。

    **CIF 提示**
    - 只说明 CIF 文件已保存到本地以及文件名。

    - 如果是搜索结果，使用 Markdown 表格列出候选材料。
    - 不要展示内部推理过程，不要暴露 tool_calls、trace、工作流等内部实现。
    """
).strip()

MAX_TOOL_ROUNDS = 6


def _done(name: str, t0: float, data: dict[str, Any], fallback: bool = False) -> StepResult:
    return StepResult(
        step_name=name,
        status=StepStatus.SUCCESS,
        data=data,
        latency_ms=int((time.time() - t0) * 1000),
        fallback_used=fallback,
    )


def _fail(name: str, t0: float, code: ErrorCode, msg: str, data: dict[str, Any] | None = None) -> StepResult:
    return StepResult(
        step_name=name,
        status=StepStatus.FAILED,
        data=data or {},
        error_code=code.value,
        error_message=msg,
        latency_ms=int((time.time() - t0) * 1000),
    )


def _normalize_content(content: Any) -> str:
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                text = item.get("text")
                if isinstance(text, str) and text.strip():
                    parts.append(text.strip())
        return "\n".join(parts).strip()
    return ""


def _safe_json_load(text: str) -> dict[str, Any]:
    try:
        data = json.loads(text or "{}")
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _tool_result_to_content(result: Any) -> str:
    if isinstance(result, str):
        return result
    if isinstance(result, dict):
        # For search results with ok/data shape, serialize the data for the LLM
        if "ok" in result and "data" in result:
            if result.get("ok") and result["data"]:
                return json.dumps(result["data"], ensure_ascii=False)
            note = result.get("note") or result.get("error") or "无结果"
            return note
        sanitized = dict(result)
        sanitized.pop("cif", None)
        return json.dumps(sanitized, ensure_ascii=False)
    return json.dumps(result, ensure_ascii=False)


def _tool_result_for_context(result: Any) -> Any:
    if isinstance(result, dict):
        # For search results with ok/data shape, unwrap for the LLM context
        if "ok" in result:
            if result.get("ok") and result.get("data"):
                return {"results": result["data"]}
            return {"note": result.get("note") or result.get("error") or "无结果"}
        sanitized = dict(result)
        sanitized.pop("cif", None)
        return sanitized
    return result


def _update_context_from_tool(ctx: WorkflowContext, tool_name: str, result: Any) -> None:
    if tool_name == "search_materials_by_criteria":
        items: list[dict[str, Any]] = []
        if isinstance(result, dict):
            if not result.get("ok", False):
                pass  # error — items stays empty
            elif isinstance(result.get("data"), list):
                items = result["data"]
        elif isinstance(result, str) and result.strip().startswith("["):
            try:
                parsed = json.loads(result)
                if isinstance(parsed, list):
                    items = [row for row in parsed if isinstance(row, dict)]
            except Exception:
                pass
        ctx.retrieval_result = {"items": items}
        return

    if tool_name != "get_mp_structure" or not isinstance(result, dict) or result.get("error"):
        return

    ctx.structure_result = result
    ctx.slots["mp_id"] = result.get("mp_id")
    ctx.slots["formula"] = result.get("formula")

    cif_path = result.get("cif_path")
    if not cif_path:
        return

    fname, lat, comp, xrd = get_cif_info(cif_path)
    if not fname:
        return

    ctx.viz_result = {
        "filename": fname,
        "cif_path": cif_path,
        "lattice_df": lat,
        "comp_df": comp,
        "xrd_df": xrd,
    }


def _fallback_answer(ctx: WorkflowContext) -> str:
    structure = ctx.structure_result or {}
    items = (ctx.retrieval_result or {}).get("items", [])

    if structure:
        formula = structure.get("formula", "N/A")
        mp_id = structure.get("mp_id", "N/A")
        crystal = structure.get("crystal_system", "N/A")
        spg = structure.get("spacegroup_symbol", "N/A")
        num = structure.get("spacegroup_number", "N/A")
        return (
            f"已获取 {formula} ({mp_id}) 的结构信息。\n\n"
            f"- 晶系：{crystal}\n"
            f"- 空间群：{spg} (No.{num})\n"
            "- 已生成并保存对应 CIF，可在界面中查看解析结果。"
        )

    if items:
        preview = "\n".join(
            f"- {row.get('MP_ID', 'N/A')} | {row.get('Formula', 'N/A')} | {row.get('Band_Gap', 'N/A')}"
            for row in items[:5]
        )
        return (
            "已完成材料检索，候选结果如下：\n"
            f"{preview}\n\n"
            "如果你要继续查看其中某个材料的具体结构，请告诉我对应的 MP-ID 或化学式。"
        )

    return "没有得到可用的工具结果，请提供更明确的 MP-ID、化学式或筛选条件。"


def _validate_answer_against_facts(answer: str, ctx: WorkflowContext) -> bool:
    """Check that the LLM answer includes the correct formula and mp_id from the structure result."""
    structure = ctx.structure_result or {}
    formula = str(structure.get("formula") or "").strip()
    mp_id = str(structure.get("mp_id") or "").strip().lower()

    if not formula and not mp_id:
        return True  # no known facts to check against

    lower_answer = answer.lower()

    if formula and formula.lower() not in lower_answer:
        return False
    if mp_id and mp_id not in lower_answer:
        return False

    # Reject if the answer mentions any extra mp-ids that don't match the known one
    if mp_id:
        all_mp_ids = set(re.findall(r"\bmp-\d+\b", lower_answer))
        if all_mp_ids and all_mp_ids != {mp_id}:
            return False

    return True


def _final_answer_from_context(ctx: WorkflowContext) -> str | None:
    facts: dict[str, Any] = {
        "question": ctx.question,
        "structure": _tool_result_for_context(ctx.structure_result),
        "retrieval_items": (ctx.retrieval_result or {}).get("items", []),
    }

    viz = ctx.viz_result or {}
    lat = viz.get("lattice_df")
    if lat is not None and not lat.empty:
        facts["lattice"] = [
            {
                "parameter": str(row["Parameter"]),
                "value": float(row["Value"]),
                "unit": str(row["Unit"]),
            }
            for _, row in lat.iterrows()
        ]

    try:
        message = create_chat_completion(
            [
                {"role": "system", "content": FINAL_ANSWER_PROMPT},
                {
                    "role": "user",
                    "content": (
                        "请基于以下事实生成最终回答。禁止编造，禁止输出原始 CIF 文本。\n\n"
                        + json.dumps(facts, ensure_ascii=False)
                    ),
                },
            ],
            temperature=0.1,
            max_tokens=900,
            tool_choice="none",
        )
    except LLMClientError:
        return None

    answer = _normalize_content(message.get("content"))
    if not answer:
        return None

    if not _validate_answer_against_facts(answer, ctx):
        return None  # caller falls back to _fallback_answer

    return answer


class WorkflowOrchestrator:
    def run(self, question: str) -> WorkflowContext:
        stream = self.run_stream(question)
        while True:
            try:
                next(stream)
            except StopIteration as stop:
                return stop.value

    def run_stream(self, question: str) -> Generator[dict[str, Any], None, WorkflowContext]:
        ctx = WorkflowContext(question=question, trace_id=str(uuid.uuid4()))
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": question},
        ]

        round_idx = 0
        final_answer = ""

        while round_idx < MAX_TOOL_ROUNDS:
            round_idx += 1
            llm_t0 = time.time()
            yield {"type": "step_start", "step": "function_calling"}

            try:
                assistant_message = create_chat_completion(
                    messages,
                    temperature=0.1,
                    max_tokens=1200,
                    tools=OPENAI_TOOL_SPECS,
                    tool_choice="auto",
                )
            except LLMClientError as e:
                result = _fail("function_calling", llm_t0, ErrorCode.ANSWER_COMPOSE_FAILED, str(e))
                ctx.step_results.append(result)
                yield {
                    "type": "step_end",
                    "step": result.step_name,
                    "status": result.status.value,
                    "latency_ms": result.latency_ms,
                    "error": result.error_message,
                    "fallback_used": result.fallback_used,
                }
                break

            tool_calls = assistant_message.get("tool_calls") or []
            assistant_msg: dict[str, Any] = {
                "role": "assistant",
                "content": assistant_message.get("content"),
            }
            if tool_calls:
                assistant_msg["tool_calls"] = tool_calls
            messages.append(assistant_msg)

            if tool_calls:
                result = _done(
                    "function_calling",
                    llm_t0,
                    {"round": round_idx, "tool_calls": len(tool_calls)},
                )
                ctx.step_results.append(result)
                yield {
                    "type": "step_end",
                    "step": result.step_name,
                    "status": result.status.value,
                    "latency_ms": result.latency_ms,
                    "error": result.error_message,
                    "fallback_used": result.fallback_used,
                }
            else:
                content = _normalize_content(assistant_message.get("content"))
                if ctx.structure_result or (ctx.retrieval_result or {}).get("items"):
                    content = _final_answer_from_context(ctx) or content
                final_answer = content
                result = _done(
                    "answer_composition",
                    llm_t0,
                    {"round": round_idx, "answer_len": len(content), "source": "llm_function_calling"},
                )
                ctx.step_results.append(result)
                yield {
                    "type": "step_end",
                    "step": result.step_name,
                    "status": result.status.value,
                    "latency_ms": result.latency_ms,
                    "error": result.error_message,
                    "fallback_used": result.fallback_used,
                }
                break

            for tool_call in tool_calls:
                tool_t0 = time.time()
                fn = (tool_call.get("function") or {}).get("name", "")
                args_text = (tool_call.get("function") or {}).get("arguments", "")
                tool_call_id = tool_call.get("id")
                yield {"type": "step_start", "step": fn}

                arguments = _safe_json_load(args_text)
                result_payload = execute_openai_tool(fn, arguments)
                _update_context_from_tool(ctx, fn, result_payload)

                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call_id,
                        "name": fn,
                        "content": _tool_result_to_content(result_payload),
                    }
                )

                error_message = None
                if isinstance(result_payload, dict):
                    error_message = result_payload.get("error")

                if error_message:
                    if fn == "get_mp_structure":
                        code = ErrorCode.CIF_PARSE_FAILED
                    elif fn == "search_materials_by_criteria":
                        code = ErrorCode.MP_API_EMPTY_RESULT
                    else:
                        code = ErrorCode.MP_API_EMPTY_RESULT
                    tool_result = _fail(fn, tool_t0, code, str(error_message), {"arguments": arguments})
                else:
                    tool_result = _done(fn, tool_t0, {"arguments": arguments})

                ctx.step_results.append(tool_result)
                yield {
                    "type": "step_end",
                    "step": tool_result.step_name,
                    "status": tool_result.status.value,
                    "latency_ms": tool_result.latency_ms,
                    "error": tool_result.error_message,
                    "fallback_used": tool_result.fallback_used,
                }

                if fn == "get_mp_structure" and ctx.viz_result.get("filename"):
                    viz_result = _done(
                        "visualization_generation",
                        tool_t0,
                        {"ready": True, "filename": ctx.viz_result.get("filename")},
                    )
                    ctx.step_results.append(viz_result)
                    yield {
                        "type": "step_end",
                        "step": viz_result.step_name,
                        "status": viz_result.status.value,
                        "latency_ms": viz_result.latency_ms,
                        "error": viz_result.error_message,
                        "fallback_used": viz_result.fallback_used,
                    }

        if not final_answer:
            fallback_t0 = time.time()
            final_answer = _fallback_answer(ctx)
            fallback_result = _done(
                "answer_composition",
                fallback_t0,
                {"answer_len": len(final_answer), "source": "template"},
                fallback=True,
            )
            ctx.step_results.append(fallback_result)

        ctx.final_answer = final_answer

        yield {
            "type": "final",
            "trace_id": ctx.trace_id,
            "answer": ctx.final_answer,
            "viz": ctx.viz_result,
            "step_results": [
                {
                    "step_name": s.step_name,
                    "status": s.status.value,
                    "latency_ms": s.latency_ms,
                    "error_code": s.error_code,
                    "error_message": s.error_message,
                    "fallback_used": s.fallback_used,
                }
                for s in ctx.step_results
            ],
        }

        return ctx
