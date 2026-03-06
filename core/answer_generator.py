from __future__ import annotations

import json
import re
from textwrap import dedent
from typing import Any

from core.llm_client import LLMClientError, chat_completion
from core.workflow_types import WorkflowContext


ANSWER_INSTRUCTIONS = dedent(
    """
    总体原则：
    - 默认使用中文回答。
    - 面向材料科学研究生用户，专业且清晰。

    === 核心规则 1：格式规范 (必须严格遵守) ===
    为了前端渲染和阅读体验，请严格遵守 LaTeX 格式：
    1. 化学式：必须用 LaTeX。例：不要写 LiFePO4，要写 $\\text{LiFePO}_4$；不要写 Fe2+，要写 $\\text{Fe}^{2+}$。
    2. 晶格参数/单位：例：$\\alpha, \\beta, \\gamma$, $90^\\circ$, $\\text{\\AA}$。
    3. 空间群：例：$Pbnm$ 或 $Fd\\bar{3}m$。
    4. 数学符号：例：$x, y, z$。

    === 核心规则 2：工具选择策略 (NL-to-Query) ===
    根据用户意图选择工具：

    【场景 A：模糊搜索/筛选】
    - 当用户描述筛选条件时（如 "找带隙大于2eV的铁基材料"、"筛选稳定的立方氧化物"）。
    - **操作**：调用 `search_materials_by_criteria`。
    - **参数提取技巧**：
        * "绝缘体" -> `band_gap_min` > 2.0
        * "半导体" -> `band_gap_min` > 0
        * "稳定" -> `is_stable=True`
    - **回答格式**：使用 Markdown 表格列出搜索结果（ID、化学式、带隙、空间群），并在最后提示用户："如需查看具体结构，请告诉我 MP-ID。"

    【场景 B：查看具体结构详情】
    - 当用户指定 MP-ID (如 mp-149) 或具体材料名希望分析结构时。
    - **操作**：调用 `get_mp_structure`。
    - **回答格式**（分点作答）：
        1. **概览**：材料名、MP-ID、晶系、空间群。
        2. **结构特征**：晶格参数（简述）、配位多面体（如 $FeO_6$ 八面体）、连接方式（共顶点/共棱/共面）。
        3. **性质关联**：若用户提及，分析离子通道或电子结构特征。
        4. **CIF 提示**：文末说明 "对应的 CIF 文件已保存..."。

    请根据用户的输入，智能判断进入【场景 A】还是【场景 B】。
    """
).strip()


CLASSIFIER_PROMPT = dedent(
    """
    你是意图分类器。输出严格 JSON，字段如下：
    {
      "intent": "SEARCH" | "STRUCTURE_DETAIL" | "HYBRID",
      "confidence": 0~1,
      "slots": {
        "mp_id": string|null,
        "formula": string|null,
        "elements": string[]|null,
        "band_gap_min": number|null,
        "band_gap_max": number|null,
        "is_stable": bool|null,
        "crystal_system": string|null
      }
    }
    只输出 JSON，不要解释。
    """
).strip()


def _safe_json_load(text: str) -> dict[str, Any] | None:
    text = text.strip()
    if not text:
        return None

    try:
        return json.loads(text)
    except Exception:
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                return json.loads(text[start : end + 1])
            except Exception:
                return None
        return None


def classify_intent_with_llm(question: str) -> dict[str, Any] | None:
    try:
        out = chat_completion(
            [
                {"role": "system", "content": CLASSIFIER_PROMPT},
                {"role": "user", "content": question},
            ],
            temperature=0.0,
            max_tokens=220,
        )
    except LLMClientError:
        return None

    data = _safe_json_load(out)
    if not data:
        return None

    intent = str(data.get("intent", "")).upper()
    if intent not in {"SEARCH", "STRUCTURE_DETAIL", "HYBRID"}:
        return None

    try:
        confidence = float(data.get("confidence", 0.0))
    except Exception:
        confidence = 0.0
    confidence = max(0.0, min(1.0, confidence))

    slots = data.get("slots") or {}
    if not isinstance(slots, dict):
        slots = {}

    return {
        "intent": intent,
        "confidence": confidence,
        "slots": slots,
    }


def _summarize_facts(ctx: WorkflowContext) -> dict[str, Any]:
    facts: dict[str, Any] = {
        "intent": ctx.intent,
        "slots": ctx.slots,
        "structure": ctx.structure_result,
        "retrieval_items": (ctx.retrieval_result or {}).get("items", []),
    }

    viz = ctx.viz_result or {}
    lat = viz.get("lattice_df")
    comp = viz.get("comp_df")
    xrd = viz.get("xrd_df")

    if lat is not None and not lat.empty:
        facts["lattice"] = [
            {
                "parameter": str(row["Parameter"]),
                "value": float(row["Value"]),
                "unit": str(row["Unit"]),
            }
            for _, row in lat.iterrows()
        ]

    if comp is not None and not comp.empty:
        facts["composition"] = [
            {
                "element": str(row["Element"]),
                "count": float(row["Count"]),
                "fraction": float(row["Fraction"]),
            }
            for _, row in comp.iterrows()
        ]

    if xrd is not None and not xrd.empty:
        top = xrd.sort_values("Intensity", ascending=False).head(5)
        facts["xrd_top_peaks"] = [
            {
                "two_theta": float(row["2Theta"]),
                "intensity": float(row["Intensity"]),
                "hkl": str(row["HKL"]),
            }
            for _, row in top.iterrows()
        ]

    return facts


def _sanitize_answer(text: str) -> str:
    t = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    if "\\n" in t:
        t = t.replace("\\n", "\n")
    return t


def _validate_answer_against_facts(ctx: WorkflowContext, answer: str) -> bool:
    structure = ctx.structure_result or {}
    formula = str(structure.get("formula") or "").strip()
    mp_id = str(structure.get("mp_id") or "").strip().lower()

    if not formula and not mp_id:
        return True

    lower_answer = answer.lower()

    # If structure exists, generated answer must explicitly include the same formula/mp-id.
    if formula and formula.lower() not in lower_answer:
        return False
    if mp_id and mp_id not in lower_answer:
        return False

    # If any mp-id is mentioned, all of them must match the expected one.
    if mp_id:
        all_mp_ids = set(re.findall(r"\bmp-\d+\b", lower_answer))
        if all_mp_ids and all_mp_ids != {mp_id}:
            return False

    return True


def generate_answer_with_llm(ctx: WorkflowContext) -> str | None:
    facts = _summarize_facts(ctx)

    user_prompt = dedent(
        f"""
        用户问题：{ctx.question}

        已完成的工作流意图：{ctx.intent}

        事实数据（唯一可信来源，严禁编造）：
        {json.dumps(facts, ensure_ascii=False)}

        你的任务：
        1. 生成面向用户的最终回答，而不是流程日志。
        2. 不要暴露“工作流步骤/状态/trace”等内部信息。
        3. 必须解释数据意义，不要只罗列数值。
        4. 若信息缺失，明确说明“当前数据不足以判断”。
        5. 若已有结构结果，必须逐字包含准确的材料标识：formula 和 mp_id，不得替换为其他材料。
        """
    ).strip()

    try:
        out = chat_completion(
            [
                {
                    "role": "system",
                    "content": ANSWER_INSTRUCTIONS
                    + "\n\n补充约束：当前只负责最终回答写作，不再调用任何工具。",
                },
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.25,
            max_tokens=900,
        )
    except LLMClientError:
        return None

    out = _sanitize_answer(out)
    if len(out) < 60:
        return None
    if not _validate_answer_against_facts(ctx, out):
        return None
    return out
