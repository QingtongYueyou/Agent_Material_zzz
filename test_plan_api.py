"""测试 /api/v1/plan 端点 — 支持本地和公网"""
import json
import sys
import urllib.request

# 默认本地，传 --public 走公网
BASE_URL = "http://127.0.0.1:8080"
if "--public" in sys.argv:
    BASE_URL = "https://discrete-nathan-endorsed-properly.trycloudflare.com"

url = f"{BASE_URL}/api/v1/plan"

# 可以自己改 query 测试不同场景
body = json.dumps({
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
}).encode("utf-8")

print(f"目标: {url}")
print(f"请求: {json.loads(body)['query']}")
print("-" * 50)

req = urllib.request.Request(
    url,
    data=body,
    headers={"Content-Type": "application/json"},
    method="POST",
)

with urllib.request.urlopen(req, timeout=30) as resp:
    result = json.loads(resp.read().decode("utf-8"))
    print(json.dumps(result, ensure_ascii=False, indent=2))
