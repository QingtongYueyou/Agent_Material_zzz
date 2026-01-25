# material_chatbot.py

import os
from pathlib import Path
from textwrap import dedent
from dotenv import load_dotenv

# 加载 .env 文件
load_dotenv()

from agno.agent import Agent
from agno.models.openai import OpenAIChat
from agno.tools import tool

from mp_api.client import MPRester
from pymatgen.symmetry.analyzer import SpacegroupAnalyzer

# =========================
# 基本配置
# =========================

# Materials Project 的 API Key
# 建议在系统环境变量中设置 MP_API_KEY 或 MAPI_KEY
MP_API_KEY = os.environ.get("MP_API_KEY") or os.environ.get("MAPI_KEY")

# 获取 Poe 的配置
poe_api_key = os.getenv("POE_API_KEY")
poe_base_url = os.getenv("POE_API_BASE_URL", "https://api.poe.com/v1") # 默认使用官方地址

# 当前脚本所在目录
BASE_DIR = Path(__file__).resolve().parent

# 用于存放 CIF 文件的目录
CIF_DIR = BASE_DIR / "cif_files"
CIF_DIR.mkdir(parents=True, exist_ok=True)


# =========================
# 工具：从 MP 获取结构并保存 CIF
# =========================

@tool(show_result=False)
def get_mp_structure(identifier: str) -> dict:
    """
    从 Materials Project 获取结构信息，并导出 CIF 到本地文件。

    参数:
        identifier: 可以是 mp-id（例如 "mp-149"）或者化学式（例如 "LiFePO4"）

    返回:
        - mp_id: 实际使用的 MP-ID
        - formula: 约化化学式
        - spacegroup_symbol: 空间群符号 (如 Pnma)
        - spacegroup_number: 空间群序号 (如 62)
        - cif_path: 本地保存的 CIF 文件路径（字符串）
        - cif: CIF 文本（给 LLM 使用，不建议直接整段输出给用户）
        - error: （可选）如果找不到结果，会返回 error 字段
    """


    if MP_API_KEY is None:
        return {
            "error": "MP_API_KEY 未设置，请在环境变量中配置 Materials Project 的 API key。"
        }

    with MPRester(MP_API_KEY) as mpr:
        # 1）按 mp-id 获取
        if identifier.startswith("mp-"):
            structure = mpr.get_structure_by_material_id(identifier)
            mp_id = identifier
        # 2）否则按化学式搜索，取第一个结果
        else:
            docs = mpr.materials.summary.search(
                formula=identifier,
                fields=["material_id", "structure"],
            )
            if not docs:
                return {"error": f"在 Materials Project 中找不到匹配 {identifier} 的材料。"}

            doc = docs[0]
            mp_id = str(doc.material_id)
            structure = doc.structure

    sga = SpacegroupAnalyzer(structure)
    spg_symbol = sga.get_space_group_symbol()
    spg_number = sga.get_space_group_number()
    formula, _ = structure.composition.get_reduced_formula_and_factor()

    cif_text = structure.to(fmt="cif")

    # 文件名形如 mp-12345_LiFePO4.cif
    filename = f"{mp_id}_{formula}.cif".replace("/", "-")
    cif_path = CIF_DIR / filename
    cif_path.write_text(cif_text, encoding="utf-8")

    return {
        "mp_id": mp_id,
        "formula": formula,
        "spacegroup_symbol": spg_symbol,
        "spacegroup_number": spg_number,
        "cif_path": str(cif_path),
        "cif": cif_text,
    }


# =========================
# 工具：多材料高级搜索 (NL-to-Query)
# =========================
import json  # 记得在文件顶部确保引入 json，或者直接在这里用


@tool(show_result=False)
def search_materials_by_criteria(
    elements: list[str] = None,
    band_gap_min: float = None,
    band_gap_max: float = None,
    is_stable: bool = None,
    crystal_system: str = None,
    max_results: int = 10
) -> str:
    """
    根据筛选条件搜索材料列表。

    参数:
        elements: 元素列表，例如 ["Li", "Fe"]。
        band_gap_min: 最小带隙 (eV)。
        band_gap_max: 最大带隙 (eV)。
        is_stable: 是否仅搜索稳定材料。
        crystal_system: 晶系。
        max_results: 最大结果数。
    """
    if MP_API_KEY is None:
        return "Error: MP_API_KEY 未设置。"

    with MPRester(MP_API_KEY) as mpr:
        try:
            # === 1. 修复 Pydantic 报错的关键配置 ===
            # 使用 fields 精确指定字段，避免触发旧版库的校验 bug
            search_kwargs = {
                "num_chunks": 1,
                "chunk_size": 1000,
                "fields": ["material_id", "formula_pretty", "band_gap", "is_stable", "symmetry"]
            }

            if elements:
                search_kwargs["elements"] = elements

            if band_gap_min is not None or band_gap_max is not None:
                search_kwargs["band_gap"] = (band_gap_min, band_gap_max)

            if is_stable is not None:
                search_kwargs["is_stable"] = is_stable

            if crystal_system:
                search_kwargs["crystal_system"] = crystal_system

            # 执行搜索
            results = mpr.materials.summary.search(**search_kwargs)

            if not results:
                return "未找到符合条件的材料，请尝试放宽筛选条件。"

            # === 2. 解决“显示两遍”的关键修改 ===
            # 不要在这里拼接 Markdown 表格！只返回纯数据列表。
            # 让 Agent (GPT) 去决定怎么画表格。

            data_list = []
            for doc in results[:max_results]:
                spg = doc.symmetry.symbol if doc.symmetry else "N/A"
                bg = f"{doc.band_gap:.2f}" if doc.band_gap is not None else "N/A"

                # 构建纯字典数据
                item = {
                    "MP_ID": doc.material_id,
                    "Formula": doc.formula_pretty,
                    "Band_Gap": f"{bg} eV",
                    "Symmetry": spg
                }
                data_list.append(item)

            # 返回 JSON 字符串，AI 读起来很方便，用户界面不会直接渲染它
            return json.dumps(data_list, ensure_ascii=False)

        except TypeError as te:
            # 捕获兼容性错误
            if "default_factory" in str(te):
                return "系统错误：库版本冲突。请尝试升级 mp-api 或使用当前的兼容模式代码。"
            return f"参数类型错误: {str(te)}"
        except Exception as e:
            return f"搜索 API 调用出错: {str(e)}"

# =========================
# 材料结构问答 Agent 定义
# =========================

materials_agent = Agent(
    name="MatStructBot",
    model=OpenAIChat(
        id="GPT-4o",
        api_key=poe_api_key,
        base_url=poe_base_url
    ),
    tools=[get_mp_structure, search_materials_by_criteria],
    description=dedent("""
        You are an expert in computational materials science and crystallography.
        You can Look up specific structures details OR Search for materials matching specific criteria.
    """),
    instructions=dedent("""
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
    """),
    markdown=True,
    add_datetime_to_context=True,
)
# =========================
# 简单命令行示例
# =========================

if __name__ == "__main__":
    # 你可以改成自己想问的问题
    question = (
        "我对 LiFePO4 正极材料感兴趣，帮我从 Materials Project 获取结构并介绍它的晶体结构特点"
        "包括晶体系统、空间群、主要配位多面体，以及 Li+ 迁移通道的大致方向。"
        "帮我筛选一些稳定的、带隙大于 2eV 的锂铁（Li, Fe）化合物，并以表格形式展示前 5 个结果。"
    )
    materials_agent.print_response(question, stream=True)
