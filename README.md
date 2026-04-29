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

推荐使用已有测试环境：

```bash
conda activate agno-assist
```

### 启动 Streamlit 应用

```bash
streamlit run app.py
```

### 启动 Planner API

```bash
uvicorn api.main:app --host 127.0.0.1 --port 8000
```

如果当前 shell 无法正常激活 conda，可以直接使用环境 Python：

```powershell
C:\Users\wyfz\.conda\envs\agno-assist\python.exe -m uvicorn api.main:app --host 127.0.0.1 --port 8000
```

健康检查：

```bash
curl http://127.0.0.1:8000/health
```

Planner API 调用示例：

```bash
curl -X POST http://127.0.0.1:8000/api/v1/plan \
  -H "Content-Type: application/json" \
  -d '{"query":"展示 LiFePO4 的晶体结构和 XRD 图谱","context":{"available_tools":["material.get_structure_file","visualization.render_3dgs","visualization.render_lattice","visualization.render_composition","visualization.render_xrd"]}}'
```

PowerShell 示例：

```powershell
$body = @{
  query = "展示 LiFePO4 的晶体结构和 XRD 图谱"
  context = @{
    available_tools = @(
      "material.get_structure_file",
      "visualization.render_3dgs",
      "visualization.render_lattice",
      "visualization.render_composition",
      "visualization.render_xrd"
    )
  }
} | ConvertTo-Json -Depth 6

Invoke-RestMethod `
  -Method Post `
  -Uri "http://127.0.0.1:8000/api/v1/plan" `
  -ContentType "application/json" `
  -Body $body
```

## HTTPS 暴露给服务器 A

本地开发联调推荐使用 Cloudflare Tunnel：

```bash
cloudflared tunnel --url http://127.0.0.1:8000
```

将生成的 HTTPS 地址提供给服务器 A，例如：

```text
POST https://example.trycloudflare.com/api/v1/plan
```

如启用鉴权，请在 `.env` 中设置：

```env
PLAN_API_TOKEN=replace-with-a-shared-secret
```

服务器 A 请求时带上：

```http
Authorization: Bearer replace-with-a-shared-secret
```

详细说明见 `docs/PLANNER_API.md`。

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
