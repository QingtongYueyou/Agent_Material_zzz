# External Materials Console

这是一个独立运行的演示系统。它不导入 Agent Material 的 `api`、`core` 或 `services` 模块，只通过 HTTP 调用 Agent Material API。用户只输入自然语言并可选上传文件，LLM 自动完成意图识别、文件理解和 MCP 工具选择。

## 启动

先启动 Agent Material 主 API 和 3DGS MCP，然后在项目根目录执行：

```powershell
.\demo\external_consumer\start.ps1
```

浏览器访问：

```text
http://127.0.0.1:3000
```

指定其他上游地址：

```powershell
.\demo\external_consumer\start.ps1 -UpstreamApi http://192.168.1.20:8080
```

## 调用边界

浏览器只调用 Demo 后端；Demo 后端再请求 Agent Material：

```text
GET  /api/visualizations/capabilities
POST /api/files/upload
POST /api/chat
```

文件是可选的：上传时先获得 `file_id` 并随自然语言请求发送；不上传时，LLM 可以调用 Materials Project 查询材料并生成系统文件。LLM 随后调用 `render_with_mcp`，自动选择外部材料 MCP 或本地 `3dgs.create_render`，最终返回可嵌入的 `artifacts[].render_url`。

建议演示指令：

```text
查询 LiFePO4 的晶体结构，并使用 3DGS MCP 进行可视化
查询 LiFePO4 的晶体结构，并调用外部结构可视化 MCP 展示
分析我上传的文件，识别其材料数据类型并调用最合适的 MCP 工具进行可视化
```
