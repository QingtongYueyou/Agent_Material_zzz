# Agent 项目总览

## 项目定位
这是一个面向材料科学场景的智能分析应用，同时支持两种运行模式：

- **Streamlit 一体化应用**：本项目自己完成用户对话、Materials Project 查询、CIF 解析、3D/图表可视化和中文回答生成。
- **服务器 B Planner API**：接收服务器 A 转发的自然语言指令，用 LLM 转换成服务器 A 可解析执行的 `tool_calls` JSON；后续数据库查询、文件获取、WebSocket 推送、前端可视化和最终回答由服务器 A 完成。

核心能力包括：
- 根据用户问题进行意图识别
- 调用 Materials Project 获取材料结构
- 解析 CIF 并生成晶体结构相关数据
- 渲染 3D 与图表可视化
- 生成面向用户的中文分析回答
- 输出跨系统集成用的工具调用 JSON

## 目录结构
- `api/`：FastAPI Planner API 入口
- `config/`：配置与环境变量管理
- `core/`：工作流编排、工具调用、数据处理、LLM 生成、Planner JSON 生成
- `docs/`：接口与部署说明
- `ui/`：前端组件、样式、可视化渲染
- `static/`：静态资源目录
- `static/splat_files/`：3D Gaussian Splatting 模型文件目录，本地放置 `.ply/.splat/.ksplat` 资产
- `cif_files/`：CIF 缓存目录
- `metrics/`：3DGS 渲染/交互性能数据和分析脚本

注意：`static/splat_files/*.ply`、`metrics/raw/*.csv`、`metrics/raw/*.ply` 属于本地生成数据或大体积资产，默认被 `.gitignore` 忽略，不再随 Git 仓库分发。需要 3DGS 可视化时，请将模型文件放入 `static/splat_files/`。

## Streamlit 主流程
1. 用户在 `app.py` 发起问题输入。
2. `core/workflow.py` 使用 function calling 决定是否调用材料检索或结构工具。
3. `core/tools.py` 调用 MP API 并写入 CIF。
4. `core/processor.py` 解析本次 CIF 生成晶格、组分、XRD 数据。
5. `ui/visualization.py` 渲染 3DGS 与图表。
6. 工作流基于事实数据生成最终回答，失败时回退模板。

## Planner API 主流程
1. 服务器 A 将用户自然语言和上下文通过 HTTP POST 发给本项目。
2. `api/main.py` 接收请求，可选校验 `PLAN_API_TOKEN`。
3. `core/planner.py` 调用现有 LLM client，将自然语言转换为严格 JSON。
4. `core/planner_schema.py` 校验并清洗工具调用。
5. 服务器 B 返回 `tool_calls`，由服务器 A 执行查库、取文件、WebSocket 推送和前端渲染。

示例响应：

```json
{
  "intent": "structure_visualization",
  "confidence": 0.93,
  "clarification_needed": false,
  "tool_calls": [
    {
      "tool": "material.get_structure_file",
      "arguments": {
        "formula": "LiFePO4",
        "mp_id": null,
        "file_type": "cif"
      }
    },
    {
      "tool": "visualization.render_xrd",
      "arguments": {
        "wavelength": "CuKa"
      }
    }
  ]
}
```

## 启动方式

### 1. 激活环境

```bash
conda activate agno-assist
```

### 2. 启动 Streamlit 应用（本地一体化模式）

```bash
cd mytest/Agent
streamlit run app.py
```

### 3. 启动 Planner API（服务器 B 模式）

**终端 1 — 启动 FastAPI：**

```bash
conda activate agno-assist
cd mytest/Agent
uvicorn api.main:app --host 0.0.0.0 --port 8080
```

**终端 2 — 启动 Cloudflare Tunnel 暴露到公网：**

```bash
# cloudflared 二进制已放在项目根目录
mytest/Agent/cloudflared.exe tunnel --url http://127.0.0.1:8080 --protocol quic
```

启动后会打印公网 HTTPS 地址：

```
Your quick Tunnel has been created! Visit it at:
https://xxx-xxx.trycloudflare.com
```

> **注意**：如果遇到代理（如 Mihomo）拦截导致连接失败，需要：
> - 关闭 TUN 模式，或
> - 使用系统代理模式并确保 Cloudflare IP 不被拦截，或
> - 临时关闭代理

**本地验证：**

```bash
# 健康检查
curl http://127.0.0.1:8080/health

# Planner API 本地测试
curl -X POST http://127.0.0.1:8080/api/v1/plan \
  -H "Content-Type: application/json" \
  -d '{"query":"展示 LiFePO4 的晶体结构和 XRD 图谱","session_id":"s-001","context":{"current_material":null,"available_tools":["material.search","material.get_structure_file","visualization.render_3dgs","visualization.render_lattice","visualization.render_composition","visualization.render_xrd"]}}'
```

**公网验证（替换为你的 tunnel URL）：**

```bash
# Python 测试脚本（推荐，避免 Windows curl 编码问题）
python test_plan_api.py
```

或直接用 Python 代码：

```python
import urllib.request, json

url = "https://xxx-xxx.trycloudflare.com/api/v1/plan"
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

req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"}, method="POST")
with urllib.request.urlopen(req, timeout=30) as resp:
    result = json.loads(resp.read().decode("utf-8"))
    print(json.dumps(result, ensure_ascii=False, indent=2))
```

## 服务器 A 接入指南

### 完整链路

```
用户自然语言
  → 服务器 A 后端
  → HTTPS POST /api/v1/plan
  → 服务器 B（本项目）FastAPI + LLM
  → 返回 tool_calls JSON
  → 服务器 A 执行工具 / 查库 / 推送前端
```

### 请求格式

```http
POST https://xxx-xxx.trycloudflare.com/api/v1/plan
Content-Type: application/json

{
  "query": "展示 LiFePO4 的晶体结构和 XRD 图谱",
  "session_id": "s-001",
  "context": {
    "current_material": null,
    "available_tools": [
      "material.search",
      "material.get_structure_file",
      "visualization.render_3dgs",
      "visualization.render_lattice",
      "visualization.render_composition",
      "visualization.render_xrd"
    ]
  }
}
```

### 响应格式

```json
{
  "trace_id": "937f7b88-b93d-433d-b41e-3e4975536837",
  "intent": "visualize_crystal_structure_and_xrd",
  "confidence": 0.95,
  "clarification_needed": false,
  "clarification_question": null,
  "tool_calls": [
    {
      "tool": "material.get_structure_file",
      "arguments": {
        "formula": "LiFePO4",
        "mp_id": null,
        "file_type": "cif"
      }
    },
    {
      "tool": "visualization.render_3dgs",
      "arguments": {
        "formula": "LiFePO4",
        "mp_id": null,
        "preferred_model": null
      }
    },
    {
      "tool": "visualization.render_xrd",
      "arguments": {
        "wavelength": "CuKa"
      }
    }
  ],
  "server_a_execution_hint": {
    "requires_database_lookup": true,
    "requires_websocket_push": true,
    "final_answer_owner": "server_a"
  },
  "planner_meta": {
    "source": "llm",
    "available_tools": ["material.search", "material.get_structure_file", "visualization.render_3dgs", "visualization.render_lattice", "visualization.render_composition", "visualization.render_xrd"]
  }
}
```

### 可用工具列表

| 工具名 | 用途 | 关键参数 |
|--------|------|----------|
| `material.search` | 条件筛选材料 | `elements`, `formula`, `mp_id`, `band_gap_min/max`, `is_stable`, `crystal_system`, `limit` |
| `material.get_structure_file` | 获取 CIF 文件 | `formula` 或 `mp_id`, `file_type` |
| `visualization.render_3dgs` | 3D Gaussian Splatting 渲染 | `formula` 或 `mp_id`, `preferred_model` |
| `visualization.render_lattice` | 晶格参数面板 | 无 |
| `visualization.render_composition` | 组分面板 | 无 |
| `visualization.render_xrd` | 模拟 XRD 图谱 | `wavelength`（默认 `CuKa`） |

### 服务器 A 处理逻辑

1. 解析 `tool_calls` 数组，按顺序执行每个工具
2. 遇到 `material.*` 工具 → 查库 / 获取文件
3. 遇到 `visualization.*` 工具 → 通过 WebSocket 推送前端渲染
4. 最终回答由服务器 A 生成（`final_answer_owner: "server_a"`）
5. 若 `clarification_needed: true`，将 `clarification_question` 展示给用户追问

### 鉴权（可选）

在 `.env` 中设置：

```env
PLAN_API_TOKEN=your-shared-secret
```

服务器 A 请求时带上：

```http
Authorization: Bearer your-shared-secret
```

### 注意事项

- 免费 Cloudflare Tunnel 每次重启会更换 URL，适合开发测试
- 生产环境需要 Cloudflare 账号 + 命名隧道（Named Tunnel）来固定域名
- 服务器 B 只做规划，不执行任何数据库查询或文件操作
- LLM 失败时自动回退到正则规则匹配（置信度降为 0.55）

## 环境变量

- `POE_API_KEY`：LLM 调用密钥
- `POE_API_BASE_URL`：OpenAI-compatible API 地址，默认 `https://api.poe.com/v1`
- `LLM_MODEL_ID`：模型 ID，默认 `GPT-4o`
- `LLM_TIMEOUT_SEC`：LLM 超时时间
- `MP_API_KEY` 或 `MAPI_KEY`：Materials Project API key
- `PLAN_API_TOKEN`：Planner API 可选 Bearer token

## 关键依赖
- `streamlit`
- `fastapi`
- `uvicorn`
- `mp-api`
- `pymatgen`
- `agno`
- `pandas`
- `altair`
- `python-dotenv`
- `numpy`
