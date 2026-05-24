# static 目录说明

`static/` 保存可通过 FastAPI `/static` 路径访问的静态资源。

## 3DGS 资产

```text
static/splat_files/
  source/             原始 3DGS 资产
  derived/            Spark 构建后的运行时资产和 manifest
  _pipeline/          后台构建状态
  _bounds/            PLY bounds 缓存
```

React 前端调用后端接口解析资产：

```http
GET /api/assets/splat/{filename}?quality=auto
```

后端通过 `core/splat_assets.py` 返回实际可加载的模型 URL。
