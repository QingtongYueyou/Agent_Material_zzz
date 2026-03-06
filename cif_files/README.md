# cif_files 目录说明

## 目录职责
该目录用于缓存从 Materials Project 获取的 CIF 文件，是结构解析与可视化的数据输入源。

## 当前文件
- `mp-1094120_Nb.cif`
- `mp-1101521_LiFeP2O7.cif`
- `mp-1661648_LiFePO4.cif`

## 生成来源
- `core/tools.py` 中 `get_mp_structure_raw` 会按 `mp-id_formula.cif` 命名落地。

## 解析方式
- 推荐：`core/processor.py::get_cif_info(cif_path)`（按本次文件精确解析）
- 兼容：`get_latest_cif_info()`（按目录最新文件解析）

## 维护建议
- 该目录属于缓存目录，建议定期清理无用文件。
- 排查错配问题时，重点核对“请求 formula/mp-id、返回结构 formula、解析使用的 cif_path”是否一致。
