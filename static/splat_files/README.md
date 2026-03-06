# splat_files 目录说明

## 目录职责
存放 3D Gaussian Splatting 模型文件，供中栏 WebGL 视图加载。

## 当前文件
- `mp-1661648_LiFePO4.ply`
- `mp-3442_CaTiO3.ply`
- `object.ply`（通用回退模型）

## 匹配逻辑
渲染模块按以下优先级匹配模型：
1. `cif_basename` 精确匹配
2. `material_name` 匹配
3. `formula_name` 匹配
4. `glob` 模糊匹配
5. `object.ply` 回退

## 排障建议
- 若“专属模型存在但显示 object.ply”，优先检查 `viz_data.filename` 是否是本次请求对应的 CIF 文件名。
- 确认模型格式是否为支持类型：`.ply`、`.splat`、`.ksplat`。
