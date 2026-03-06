# static 目录说明

## 目录职责
`static/` 存放前端可视化所需的静态资源。

## 子目录
- `splat_files/`：3D Gaussian Splatting 模型文件

## 使用方式
- `ui/visualization.py` 会启动本地静态服务读取此目录文件。
- 3D 模型通过 `http://127.0.0.1:8001/static/splat_files/...` 加载。

## 命名建议
- 推荐：`mp-xxxx_formula.ply`
- 回退：`object.ply`

## 维护建议
- 新增模型后先验证命名是否与 CIF 文件名可匹配。
- 大体积资源建议按需管理，避免仓库无序膨胀。
