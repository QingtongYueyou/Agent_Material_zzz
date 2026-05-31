from __future__ import annotations

import json
from typing import Any

from agno.tools import tool
from mp_api.client import MPRester
from pymatgen.symmetry.analyzer import SpacegroupAnalyzer

from config.settings import CIF_DIR, MP_API_KEY


def get_mp_structure_raw(identifier: str) -> dict:
    """
    从 Materials Project 获取结构信息，并导出 CIF 到本地文件。

    参数:
        identifier: 可以是 mp-id（例如 "mp-149"）或者化学式（例如 "LiFePO4"）

    返回:
        - mp_id: 实际使用的 MP-ID
        - formula: 约化化学式
        - spacegroup_symbol: 空间群符号(如 Pnma)
        - spacegroup_number: 空间群序号(如 62)
        - cif_path: 本地保存的 CIF 文件路径（字符串）
        - cif: CIF 文本（给 LLM 使用，不建议直接整段输出给用户）
        - error: （可选）如果找不到结果，会返回 error 字段
    """
    if MP_API_KEY is None:
        return {
            "error": "MP_API_KEY 未设置，请在环境变量中配置 Materials Project 的 API key。"
        }

    with MPRester(MP_API_KEY) as mpr:
        if identifier.startswith("mp-"):
            structure = mpr.get_structure_by_material_id(identifier)
            mp_id = identifier
        else:
            target_formula = identifier.strip()
            docs = mpr.materials.summary.search(
                formula=target_formula,
                fields=["material_id", "structure", "formula_pretty"],
            )
            if not docs:
                return {"error": f"在 Materials Project 中找不到匹配 {identifier} 的材料。"}

            # Prefer exact formula match to avoid grabbing a different compound.
            exact_docs = []
            for d in docs:
                pretty = str(getattr(d, "formula_pretty", "") or "").strip()
                reduced = ""
                try:
                    reduced = str(d.structure.composition.reduced_formula).strip()
                except Exception:
                    reduced = ""
                if (
                    pretty.lower() == target_formula.lower()
                    or reduced.lower() == target_formula.lower()
                ):
                    exact_docs.append(d)

            if not exact_docs:
                return {
                    "error": (
                        f"在 Materials Project 中未找到与 {target_formula} 完全一致的化学式结果。"
                    )
                }

            doc = exact_docs[0]
            mp_id = str(doc.material_id)
            structure = doc.structure

    sga = SpacegroupAnalyzer(structure)
    spg_symbol = sga.get_space_group_symbol()
    spg_number = sga.get_space_group_number()
    crystal_system = sga.get_crystal_system()
    formula, _ = structure.composition.get_reduced_formula_and_factor()

    cif_text = structure.to(fmt="cif")

    filename = f"{mp_id}_{formula}.cif".replace("/", "-")
    cif_path = CIF_DIR / filename
    cif_path.write_text(cif_text, encoding="utf-8")

    return {
        "mp_id": mp_id,
        "formula": formula,
        "spacegroup_symbol": spg_symbol,
        "spacegroup_number": spg_number,
        "crystal_system": crystal_system,
        "cif_path": str(cif_path),
        "cif": cif_text,
    }


def search_materials_by_criteria_raw(
    elements: list[str] | None = None,
    band_gap_min: float | None = None,
    band_gap_max: float | None = None,
    is_stable: bool | None = None,
    crystal_system: str | None = None,
    max_results: int = 10,
) -> dict:
    """
    根据筛选条件搜索材料列表。

    参数:
        elements: 元素列表，例如 ["Li", "Fe"]。
        band_gap_min: 最小带隙(eV)。
        band_gap_max: 最大带隙(eV)。
        is_stable: 是否仅搜索稳定材料。
        crystal_system: 晶系。
        max_results: 最大结果数。

    返回:
        {"ok": true, "data": [...]} 或 {"ok": false, "error": "..."}
    """
    if MP_API_KEY is None:
        return {"ok": False, "error": "MP_API_KEY 未设置，请在环境变量中配置 Materials Project 的 API key。"}

    with MPRester(MP_API_KEY) as mpr:
        try:
            chunk_size = min(max(max_results, 20), 1000)
            search_kwargs = {
                "num_chunks": 1,
                "chunk_size": chunk_size,
                "fields": [
                    "material_id",
                    "formula_pretty",
                    "band_gap",
                    "is_stable",
                    "symmetry",
                ],
            }

            if elements:
                search_kwargs["elements"] = elements

            if band_gap_min is not None or band_gap_max is not None:
                search_kwargs["band_gap"] = (band_gap_min, band_gap_max)

            if is_stable is not None:
                search_kwargs["is_stable"] = is_stable

            if crystal_system:
                search_kwargs["crystal_system"] = crystal_system

            results = mpr.materials.summary.search(**search_kwargs)

            if not results:
                return {"ok": True, "data": [], "note": "未找到符合条件的材料，请尝试放宽筛选条件。"}

            data_list = []
            for doc in results[:max_results]:
                spg = doc.symmetry.symbol if doc.symmetry else "N/A"
                bg = f"{doc.band_gap:.2f}" if doc.band_gap is not None else "N/A"
                item = {
                    "MP_ID": doc.material_id,
                    "Formula": doc.formula_pretty,
                    "Band_Gap": f"{bg} eV",
                    "Symmetry": spg,
                }
                data_list.append(item)

            return {"ok": True, "data": data_list}

        except TypeError as te:
            if "default_factory" in str(te):
                return {"ok": False, "error": "系统错误：库版本冲突。请尝试升级 mp-api 或使用当前的兼容模式代码。"}
            return {"ok": False, "error": f"参数类型错误: {str(te)}"}
        except Exception as e:
            return {"ok": False, "error": f"搜索 API 调用出错: {str(e)}"}


@tool(show_result=False)
def get_mp_structure(identifier: str) -> dict:
    return get_mp_structure_raw(identifier)


@tool(show_result=False)
def search_materials_by_criteria(
    elements: list[str] | None = None,
    band_gap_min: float | None = None,
    band_gap_max: float | None = None,
    is_stable: bool | None = None,
    crystal_system: str | None = None,
    max_results: int = 10,
) -> str:
    return search_materials_by_criteria_raw(
        elements=elements,
        band_gap_min=band_gap_min,
        band_gap_max=band_gap_max,
        is_stable=is_stable,
        crystal_system=crystal_system,
        max_results=max_results,
    )


OPENAI_TOOL_SPECS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "get_mp_structure",
            "description": (
                "Retrieve a crystal structure from Materials Project by mp-id or exact formula, "
                "save its CIF locally, and return structure metadata."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "identifier": {
                        "type": "string",
                        "description": "An mp-id like mp-149 or an exact formula like LiFePO4.",
                    }
                },
                "required": ["identifier"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_materials_by_criteria",
            "description": (
                "Search Materials Project for materials matching filters such as elements, "
                "band gap range, stability, and crystal system."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "elements": {
                        "type": ["array", "null"],
                        "items": {"type": "string"},
                        "description": "Element symbols such as ['Li', 'Fe'].",
                    },
                    "band_gap_min": {
                        "type": ["number", "null"],
                        "description": "Minimum band gap in eV.",
                    },
                    "band_gap_max": {
                        "type": ["number", "null"],
                        "description": "Maximum band gap in eV.",
                    },
                    "is_stable": {
                        "type": ["boolean", "null"],
                        "description": "Whether to restrict to stable materials.",
                    },
                    "crystal_system": {
                        "type": ["string", "null"],
                        "description": "Crystal system filter.",
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "Maximum number of results to return.",
                        "default": 5,
                    },
                },
                "additionalProperties": False,
            },
        },
    },
]


def execute_openai_tool(tool_name: str, arguments: dict[str, Any]) -> Any:
    if tool_name == "get_mp_structure":
        identifier = str(arguments.get("identifier") or "").strip()
        if not identifier:
            return {"error": "identifier is required"}
        return get_mp_structure_raw(identifier)

    if tool_name == "search_materials_by_criteria":
        return search_materials_by_criteria_raw(
            elements=arguments.get("elements"),
            band_gap_min=arguments.get("band_gap_min"),
            band_gap_max=arguments.get("band_gap_max"),
            is_stable=arguments.get("is_stable"),
            crystal_system=arguments.get("crystal_system"),
            max_results=int(arguments.get("max_results") or 5),
        )

    return {"error": f"Unknown tool: {tool_name}"}
