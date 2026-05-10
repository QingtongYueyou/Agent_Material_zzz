"""快速测试 Planner API：直接调用 create_tool_plan，不经过 HTTP。"""
import json
import sys
from pathlib import Path

# 确保项目根目录在 sys.path 中
sys.path.insert(0, str(Path(__file__).resolve().parent))

from core.planner import create_tool_plan

request_body = {
    "query": "展示 LiFePO4 的晶体结构和 XRD 图谱",
    "session_id": "s-001",
    "context": {
        "current_material": None,
        "available_tools": [
            "material.search",
            "material.get_structure_file",
            "visualization.render_3dgs",
            "visualization.render_lattice",
            "visualization.render_composition",
            "visualization.render_xrd",
        ],
    },
}

print("=" * 60)
print("请求:")
print(json.dumps(request_body, ensure_ascii=False, indent=2))
print("=" * 60)

result = create_tool_plan(
    query=request_body["query"],
    session_id=request_body["session_id"],
    context=request_body["context"],
)

print("\n响应:")
print(json.dumps(result, ensure_ascii=False, indent=2))
