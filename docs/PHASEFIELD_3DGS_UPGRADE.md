# Phase-Field 3DGS 升级方案

> 适用版本:2026-06
> 目标:让相场(phase-field)3D Gaussian Splatting 数据走"Spark 离线 LoD + 分页 paged"路径,
> 同时避免浏览器误加载几百 MB 到几 GB 的原始 `.ply` 和 `*_nonzero_points.ply` 点云文件。

---

## 一、资产输入规则

### 1.1 文件类型分流

| 文件类型 | 是否 Spark 3DGS 源 | 原因 |
| --- | :---: | --- |
| `*_gaussian.ply` | ✅ | 已经包含 3DGS 字段,可直接走 Spark `build-lod` |
| `*_nonzero_points.ply` | ❌ | 普通点云,点数太大,不是 3DGS |
| `*.vtk` / `*.xyz` | ❌ | 相场标量网格,不是 Spark 可直接渲染格式 |
| `*.spz` / `*.splat` / `*.ksplat` | ✅ | 保持兼容,严格模式不影响非 PLY 后缀 |
| 已构建的 `.rad` / `.radc` | ✅ | Spark LoD + 分块分页加载,推荐路径 |

### 1.2 严格过滤开关

- 默认开启相场源文件严格过滤,只接受 `*_gaussian.ply`。
- 通过环境变量 `STRICT_PHASEFIELD_SOURCE` 控制:
  - `true`(默认):只接受 `*_gaussian.ply`,跳过其他 `.ply`。
  - `false`:接受任意 `.ply`,回到旧行为。
- 实现常量:`PHASEFIELD_3DGS_SUFFIX_PATTERN = "_gaussian"`(`core/spark_asset_ingest.py`、`tools/build_spark_assets.py`)。

### 1.3 目录约定

```text
static/splat_files/
  source/
    phase_96_color_gaussian.ply       # 只有 *_gaussian.ply 进入 ingest
    phase_1_color_gaussian.ply
  derived/
    phase_96_color_gaussian/
      phase_96_color_gaussian.manifest.json
      phase_96_color_gaussian-full-lod.rad
      phase_96_color_gaussian-full-lod-000000.radc
      ...
  _pipeline/
    spark_asset_pipeline_status.json
```

> 不要把 `*_nonzero_points.ply` 放进 `source/`,即使它不是 3DGS 源,
> 也可能被 `sync` 的兼容模式误以为是可处理文件。

---

## 二、后端构建策略

### 2.1 VARIANT_PROFILES

```python
VARIANT_PROFILES = {
    "preview":  {"method": "quick",   "max_sh": 0, "chunked": True, "suitable_for": "preview"},
    "balanced": {"method": "quality", "max_sh": 1, "chunked": True, "suitable_for": "balanced"},
    "full":     {"method": "quality", "max_sh": 3, "chunked": True, "suitable_for": "phase_field_gaussian"},
}
```

- 普通 3DGS:默认 `balanced`(`max_sh=1`,足够通用)。
- 相场 `*_gaussian.ply`:默认 `full`(`max_sh=3`,保留全部 SH 细节)。

### 2.2 sync 多 variant 构建

```bash
# 单 variant(默认 balanced)
python tools/build_spark_assets.py sync

# 相场推荐:同时构建 preview + full,manifest default_variant=full
python tools/build_spark_assets.py sync --variant preview --variant full --default-variant full

# 只登记 source 不构建 LoD
python tools/build_spark_assets.py sync --register-source-only
```

### 2.3 相场默认 variant 自动选择

`_resolve_variants_for_source()`:
- 检测文件名包含 `_gaussian`:构建顺序 = `[full, balanced, preview]`。
- 其他:`[balanced, preview, full]`(旧行为)。
- manifest 的 `default_variant` 对相场固定写入 `full`。

---

## 三、Manifest 选择顺序

`core/splat_assets.py::_select_manifest_asset` 的 fallback 顺序:

```text
requested -> default_variant -> full -> balanced -> preview -> source
```

> 旧顺序:`default -> balanced -> preview -> full -> source`(把 `full` 排太靠后,
> 不符合"质量优先"目标)。

---

## 四、资产 Record 新字段

`_build_asset_record` 现在返回:

| 字段 | 类型 | 含义 |
| --- | --- | --- |
| `recommended_quality` | `"full"` / `"balanced"` | 文件 >= 100MB 或顶点数 >= 1M 时建议 `full`,否则 `balanced` |
| `recommended_render_profile` | `"quality"` / `"performance"` | 大文件建议 `quality`(质量优先),小文件 `performance`(流畅优先) |
| `warnings` | `list[str]` | 大文件 / 超大文件 / 点云等提示 |
| `is_large_model` | `bool` | 保留兼容字段,>=100MB 或 >=1M 顶点 |

警告触发条件:

- `file_size_bytes >= 300 * 1024 * 1024`(300MB):`"source file is large; recommended to use a built variant"`
- `file_size_bytes >= 1024 * 1024 * 1024`(1GB):额外追加 `"source file is very large; direct browser loading is disabled"`
- 文件名包含 `nonzero_points`:`"this is a point cloud file; not a 3DGS renderable splat"`

API 端点透传:`/api/assets/splat/{filename}` 返回的 JSON 里现在带这三个字段;
MCP 路径 `services/three_dgs_mcp/rendering.py::asset_response` 也同步透传。

---

## 五、前端渲染档位 quality / performance

### 5.1 两个独立维度

```text
资产版本(asset quality):auto / preview / balanced / full / source
渲染策略(render profile):performance / quality
```

两者分开控制,不要混淆:
- 资产版本控制加载哪个 `.rad` / `.ply`。
- 渲染策略控制前端运行时参数(`lodScale` / `pixelRatio` 等)。

### 5.2 Render profile 参数映射

`frontend/src/components/SplatViewer.tsx::RENDER_PROFILE_PARAMS`:

| 参数 | performance | quality |
| --- | ---: | ---: |
| `lodScale` | `0.5` | `1.0` |
| `lodSplatScale` | `0.5` | `1.0` |
| `pixelRatio` | `1.0` | `min(devicePixelRatio, 1.5)` |
| `maxStdDev` | `sqrt(5)` | `sqrt(8)` |
| `minSortIntervalMs` | `16` | `0` |
| `behindFoveate` | `0.12` | `0.2` |
| `coneFov0` / `coneFov` | `80` / `110` | `90` / `120` |
| `coneFoveate` | `0.3` | `0.4` |
| `paged` | true | true |
| `pagedExtSplats` | true | true |

### 5.3 默认 profile 决策

```ts
const effectiveProfile = renderProfile
  ?? (asset?.recommended_render_profile === "quality" ? "quality" : "performance");
```

- 父组件显式传入 → 用传入值。
- 否则按后端建议字段推断。
- 字段缺失 → 默认 `performance`(兼容旧 manifest)。

### 5.4 UI 控件

`VisualizationPanel.tsx` 现在有两个独立下拉框:

```text
[资产版本 ▼] [渲染策略 ▼]
auto        流畅优先
preview     质量优先
balanced
full
source
```

---

## 六、MCP viewer 同步

`ThreeDgsMcpViewer.tsx` 和 MCP 后端都接收 `render_profile` 参数:

| 层 | 改动 |
| --- | --- |
| `frontend/api.ts` | `renderThreeDgs(filename, quality, renderProfile?, signal?)` |
| `api/schemas.py` | `ThreeDGSRenderRequest.render_profile: str = "performance"` |
| `api/main.py` | `/api/3dgs/render` 透传到 client |
| `core/3dgs_mcp_client.py` | `create_render(render_profile=...)` |
| `services/three_dgs_mcp/server.py` | 工具 `inputSchema` 接受 `render_profile` |
| `services/three_dgs_mcp/rendering.py` | `RenderSession.render_profile` 字段,持久化 |

> iframe 内部 viewer 是独立 Vite app,`render_profile` 只是记录 + 透传到 `/config`,
> 不强制影响 iframe 渲染。如需把 profile 推到 iframe viewer,需在 viewer app 内单独实现。

---

## 七、大文件保护机制

### 7.1 前端(VisualizationPanel)

切换 quality 到 `source` 时:

- `file_size_bytes >= 1 GiB` → `window.alert("源文件超过 1GB,禁止直接加载。请使用 full / balanced / preview 变体。")`,直接 return。
- `file_size_bytes >= 300 MiB` → `window.confirm("源文件 N MB,直接加载可能卡死。是否继续?")`,取消则不切。
- 其他质量档(auto/preview/balanced/full)不受影响。

警告 banner(`<div className="visual-warnings" role="alert">`)显示 `warnings` 数组里的每条文本。

### 7.2 后端(splat_assets.py)

- 大文件 / 超大文件 / nonzero_points 文件的警告已自动写入 `warnings` 字段。
- API 响应已透传。
- TODO:source variant >= 1GB 时返回 None,前端通过 `404` 兜底(当前已能在 UI 阻断,但 server 端没有强制拦截)。

> **重要**:所有 size 决策和 warning 阈值都基于 **bundle_size_bytes**,
> 不是 `.rad` header 大小。`_resolve_direct_bundle_size()` 会扫描 `<stem>-*.radc` 分块并求和;
> manifest 里有 `bundle_size_bytes` 字段时优先使用该字段。
> `.rad` header 通常只有几 KB,真实体积全在 `.radc` 分块里 —— 用 header 大小判定一定会漏报。

---

## 八、验证流程

### 8.1 单元测试

```bash
cd mytest/Agent
python -m pytest tests/ -x
```

当前 54 项全过。

### 8.2 端到端验证(用 96 color_gaussian.ply)

```bash
# 1. 把源文件放到 source/
cp "D:/清瞳月由/硕士/材料可视化/材料数据/相场/96 color_gaussian.ply" \
   static/splat_files/source/phase_96_color_gaussian.ply

# 2. 同步构建 preview + full
python tools/build_spark_assets.py sync \
    --spark-root D:/tools/spark \
    --variant preview --variant full \
    --default-variant full

# 3. 启动后端 + 前端
uvicorn api.main:app --host 127.0.0.1 --port 8080 &
cd frontend && npm run dev

# 4. 在浏览器打开 demo 链接:
#    http://127.0.0.1:5173/?demoViz=phase_96_color_gaussian

# 5. UI 操作:
#    - 资产版本选 full(默认)
#    - 渲染策略选 质量优先
#    - 切到 source 看是否会弹 alert / confirm
#    - 切到 Local 3DGS,记录 FPS 和首帧加载时间
```

### 8.3 大文件保护验证

- 把 `1 color_gaussian.ply`(假设几百 MB)放到 source 后,UI 应当自动推断 `recommended_render_profile=quality`。
- 把任意 `.ply` 改名成 `xxx_nonzero_points.ply`,UI banner 应显示 "this is a point cloud file"。
- 切到 source:
  - < 300MB:无确认
  - 300MB~1GB:confirm
  - >= 1GB:alert 直接阻断

### 8.4 MCP 路径验证

```bash
# 后端
uvicorn services.three_dgs_mcp.server:app --host 127.0.0.1 --port 8090 &
curl http://127.0.0.1:8090/health

# 前端打开 MCP 3DGS,选 full + 质量优先
# session_response 里应当包含 render_profile:"quality"
```

---

## 九、向后兼容性

- 所有新增字段都是可选,旧 manifest 仍能加载。
- `recommended_render_profile` 缺失 → 默认 `performance`(等价于原 `is_large_model=false`)。
- `STRICT_PHASEFIELD_SOURCE=false` 时,所有 `.ply` 都进入 ingest,等价于升级前行为。
- 旧 `is_large_model` 字段保留,前端不再用其切换参数,但后端 record 仍输出(方便外部监控)。

---

## 十、TODO

1. 后端 `resolve_splat_asset` 在 source variant >= 1GB 时返回 None(目前仅 UI 阻断)。
2. iframe viewer 内消费 `render_profile`,真正影响渲染参数(目前只在 metadata 里记录)。
3. `profileTouched` state 用于阻止 viz 变化时覆盖用户主动选择 —— 当前已实现 viz 变化才重置。
4. CI 增加对 `nonzero_points` 文件警告的回归测试。