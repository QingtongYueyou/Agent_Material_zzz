# config 目录说明

## 目录职责
`config/` 负责统一管理项目配置、路径常量和环境变量。

## 核心文件
- `settings.py`
  - 加载 `.env`
  - 定义路径：`CIF_DIR`、`STATIC_DIR`、`SPLAT_DIR`
  - 定义 API 配置：`MP_API_KEY`、`POE_API_KEY`、`POE_API_BASE_URL`
  - 定义 LLM 配置：`LLM_MODEL_ID`、`LLM_TIMEOUT_SEC`
- `__init__.py`
  - 包初始化文件

## 被谁使用
- `core/tools.py`：读取 MP API Key 与目录路径
- `core/llm_client.py`：读取模型调用配置
- `ui/components.py`：显示调试信息

## 维护建议
- 新增配置项统一放在 `settings.py`。
- 密钥与敏感信息只放 `.env`，不要写入代码仓库。
- 业务代码中避免硬编码路径，统一引用配置常量。
