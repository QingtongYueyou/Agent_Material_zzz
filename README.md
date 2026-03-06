# Agent 项目总览

## 项目定位
这是一个面向材料科学场景的智能分析应用，核心能力包括：
- 根据用户问题进行意图识别
- 调用 Materials Project 获取材料结构
- 解析 CIF 并生成晶体结构相关数据
- 渲染 3D 与图表可视化
- 生成面向用户的中文分析回答

## 目录结构
- `config/`：配置与环境变量管理
- `core/`：工作流编排、工具调用、数据处理、LLM 生成
- `ui/`：前端组件、样式、可视化渲染
- `static/`：静态资源目录
- `static/splat_files/`：3D Gaussian Splatting 模型文件
- `cif_files/`：CIF 缓存目录

## 主流程
1. 用户在 `app.py` 发起问题输入。
2. `core/workflow.py` 按步骤执行：意图识别 -> 检索 -> 结构解析 -> 可视化准备 -> 答案组装。
3. `core/tools.py` 调用 MP API 并写入 CIF。
4. `core/processor.py` 解析本次 CIF 生成晶格、组分、XRD 数据。
5. `ui/visualization.py` 渲染 3DGS 与图表。
6. `core/answer_generator.py` 基于事实数据生成最终回答，失败时回退模板。

## 启动方式
```bash
streamlit run app.py
```

## 关键依赖
- `streamlit`
- `mp-api`
- `pymatgen`
- `agno`


