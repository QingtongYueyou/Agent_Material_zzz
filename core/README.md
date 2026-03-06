# core 目录说明

## 目录职责
`core/` 是项目业务核心，负责从用户问题到最终回答的完整执行链路。

## 文件与功能
- `workflow_types.py`
  - 定义工作流上下文、步骤结果、状态枚举
- `workflow.py`
  - 工作流编排器（顺序执行步骤并产出事件）
- `steps.py`
  - 具体步骤实现：
    1. 意图识别
    2. 材料检索
    3. 结构解析
    4. 可视化准备
    5. 答案组装
- `tools.py`
  - MP API 工具层
  - 提供 `raw` 可调用函数与 `@tool` 包装函数
- `processor.py`
  - CIF 解析、晶格参数提取、组分统计、XRD 计算
  - 支持按指定 `cif_path` 精确解析
- `llm_client.py`
  - OpenAI-compatible 模型调用封装
- `answer_generator.py`
  - LLM 意图分类与回答生成
  - 回答一致性校验（防止材料串号）
- `agent.py`
  - 兼容保留的 Agno Agent 定义

## 架构原则
- 编排与工具分离：步骤逻辑不直接耦合外部 API 细节。
- 事实与生成分离：先拿结构化事实，再生成自然语言回答。
- 安全回退：LLM 失败或结果异常时回退模板答案。
- 一致性优先：用户明确给出 formula/mp-id 时，必须沿该标识执行。

## 数据流
1. `steps.intent` 识别意图并提取参数槽位。
2. 若有 formula/mp-id，跳过宽泛检索，直接结构解析。
3. `tools.get_mp_structure_raw` 获取结构并写入 CIF。
4. `processor.get_cif_info` 按本次 `cif_path` 解析数据。
5. `answer_generator` 基于事实生成回答并做校验。
