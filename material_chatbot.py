from __future__ import annotations

from core.agent import materials_agent
from core.tools import get_mp_structure, search_materials_by_criteria

__all__ = ["materials_agent", "get_mp_structure", "search_materials_by_criteria"]


if __name__ == "__main__":
    question = (
        "我对 LiFePO4 正极材料感兴趣，帮我从 Materials Project 获取结构并介绍它的晶体结构特点，"
        "包括晶体系统、空间群、主要配位多面体，以及 Li+ 迁移通道的大致方向。"
        "帮我筛选一些稳定的、带隙大于 2eV 的锂铁（Li, Fe）化合物，并以表格形式展示前 5 个结果。"
    )
    materials_agent.print_response(question, stream=True)
