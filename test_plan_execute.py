"""
端到端验证：Planner 返回的 tool_calls 能否真正执行并生成可视化数据。

用法：
  python test_plan_execute.py              # 本地 Planner
  python test_plan_execute.py --public     # 公网 Planner
"""
import json
import sys
import urllib.request

# ── 1. 获取 Planner 响应 ──────────────────────────────────────

BASE_URL = "http://127.0.0.1:8080"
if "--public" in sys.argv:
    BASE_URL = "https://discrete-nathan-endorsed-properly.trycloudflare.com"

url = f"{BASE_URL}/api/v1/plan"
body = json.dumps({
    "query": "展示 LiFePO4 的晶体结构和 XRD 图谱",
    "session_id": "s-test",
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

print("=" * 60)
print("步骤 1: 调用 Planner API 获取 tool_calls")
print("=" * 60)

req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"}, method="POST")
with urllib.request.urlopen(req, timeout=30) as resp:
    plan = json.loads(resp.read().decode("utf-8"))

print(f"  intent: {plan['intent']}")
print(f"  confidence: {plan['confidence']}")
print(f"  tool_calls 数量: {len(plan['tool_calls'])}")
for i, tc in enumerate(plan["tool_calls"]):
    print(f"    [{i+1}] {tc['tool']} -> {json.dumps(tc['arguments'], ensure_ascii=False)}")

# ── 2. 映射 Planner 工具名 → 本地执行函数 ─────────────────────

print("\n" + "=" * 60)
print("步骤 2: 依次执行 tool_calls")
print("=" * 60)

from core.tools import get_mp_structure_raw, search_materials_by_criteria_raw
from core.processor import get_cif_info

TOOL_MAP = {
    "material.get_structure_file": lambda args: get_mp_structure_raw(
        args.get("mp_id") or args.get("formula") or ""
    ),
    "material.search": lambda args: search_materials_by_criteria_raw(
        elements=args.get("elements"),
        band_gap_min=args.get("band_gap_min"),
        band_gap_max=args.get("band_gap_max"),
        is_stable=args.get("is_stable"),
        crystal_system=args.get("crystal_system"),
        max_results=int(args.get("limit") or 5),
    ),
}

structure_data = None
viz_data = None

for i, tc in enumerate(plan["tool_calls"]):
    tool_name = tc["tool"]
    args = tc["arguments"]
    print(f"\n  [{i+1}] 执行: {tool_name}")
    print(f"      参数: {json.dumps(args, ensure_ascii=False)}")

    if tool_name.startswith("material."):
        fn = TOOL_MAP.get(tool_name)
        if fn is None:
            print(f"      ⚠ 未映射的工具，跳过")
            continue
        result = fn(args)
        if isinstance(result, dict) and "error" in result:
            print(f"      ✗ 错误: {result['error']}")
        elif isinstance(result, str) and result.startswith("["):
            items = json.loads(result)
            print(f"      ✓ 搜索返回 {len(items)} 条结果")
            for item in items[:3]:
                print(f"        - {item.get('MP_ID')} | {item.get('Formula')} | {item.get('Band_Gap')}")
        else:
            structure_data = result
            print(f"      ✓ 获取到结构: {result.get('formula')} ({result.get('mp_id')})")
            print(f"        晶系: {result.get('crystal_system')}")
            print(f"        空间群: {result.get('spacegroup_symbol')} (No.{result.get('spacegroup_number')})")
            print(f"        CIF: {result.get('cif_path')}")

            # 解析 CIF 生成可视化数据
            cif_path = result.get("cif_path")
            if cif_path:
                fname, lat_df, comp_df, xrd_df = get_cif_info(cif_path)
                if fname:
                    viz_data = {
                        "filename": fname,
                        "lattice_df": lat_df,
                        "comp_df": comp_df,
                        "xrd_df": xrd_df,
                    }
                    print(f"      ✓ CIF 解析成功: {fname}")
                    print(f"        晶格参数: a={lat_df.iloc[0]['Value']:.3f}, b={lat_df.iloc[1]['Value']:.3f}, c={lat_df.iloc[2]['Value']:.3f} Å")
                    print(f"        元素: {', '.join(comp_df['Element'].tolist())}")
                    if xrd_df is not None and not xrd_df.empty:
                        print(f"        XRD 峰数: {len(xrd_df)}")
                    else:
                        print(f"        XRD: 无数据")

    elif tool_name.startswith("visualization."):
        if viz_data is None:
            print(f"      ⚠ 无结构数据，可视化工具需要先执行 material.get_structure_file")
        else:
            print(f"      ✓ 可视化数据已就绪（由 Streamlit 渲染）")

    else:
        print(f"      ⚠ 未知工具类型")

# ── 3. 汇总 ────────────────────────────────────────────────────

print("\n" + "=" * 60)
print("步骤 3: 验证汇总")
print("=" * 60)

if structure_data:
    print(f"  ✓ 结构数据: {structure_data.get('formula')} ({structure_data.get('mp_id')})")
else:
    print(f"  ✗ 未获取到结构数据")

if viz_data:
    print(f"  ✓ 可视化数据: {viz_data['filename']}")
    print(f"    晶格 DataFrame: {len(viz_data['lattice_df'])} 行")
    print(f"    组分 DataFrame: {len(viz_data['comp_df'])} 行")
    xrd = viz_data['xrd_df']
    print(f"    XRD DataFrame: {len(xrd)} 行" if xrd is not None and not xrd.empty else "    XRD: 无数据")
else:
    print(f"  ✗ 无可视化数据")

if structure_data and viz_data:
    print("\n  → 完整链路验证通过！可以启动 Streamlit 查看可视化效果：")
    print("    streamlit run app.py")
else:
    print("\n  → 链路不完整，请检查上方错误信息")
