# core 目录说明

`core/` 保存材料分析业务核心，不包含 FastAPI 请求对象，也不包含 React 代码。

## 主要模块

- `workflow.py`：主工作流编排器，输出 `step_start`、`step_end`、`final` 事件
- `workflow_types.py`：工作流上下文、步骤结果、状态和错误码
- `tools.py`：Materials Project 查询工具，以及 OpenAI function calling 工具描述
- `processor.py`：CIF 解析、晶格参数、组分统计和 XRD 计算
- `llm_client.py`：OpenAI-compatible LLM 调用封装
- `mcp_client.py`：MCP JSON-RPC 调用封装
- `splat_assets.py`：3DGS/Spark manifest 与直接文件解析
- `spark_asset_ingest.py`：后台 3D 资产同步和构建调度
- `perf_metrics.py`：渲染和交互指标记录

## 边界

- `core/` 可以使用 Python 对象和 Pandas DataFrame。
- 面向前端的 JSON 转换由 `api/serialization.py` 负责。
- 业务逻辑不要依赖本地开发服务器、浏览器或 React 组件。
