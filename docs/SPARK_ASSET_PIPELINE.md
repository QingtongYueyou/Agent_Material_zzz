# Spark Asset Pipeline

This project uses a manifest-first Spark asset pipeline for large 3D Gaussian Splatting assets.

## Goals

- Keep raw `.ply` / `.spz` files out of the hot runtime path
- Prefer prebuilt Spark `.rad` / `-lod.rad` variants
- Load runtime assets through manifests instead of filename guessing
- Keep the Spark toolchain outside the repo by default

## Recommended Spark toolchain layout

Preferred:

```text
D:/tools/spark
```

Also supported:

- `%USERPROFILE%/tools/spark`
- `%USERPROFILE%/spark`

Repo-local vendored Spark is still supported as a last fallback:

```text
mytest/Agent/tools/vendor/spark
```

But that path should not be the default long-term working setup, because it tends to accumulate:

- upstream `.git`
- `node_modules`
- `rust/target`
- example assets and docs

## How Spark root is resolved

The app and build tooling resolve `SPARK_ROOT` in this order:

1. `SPARK_ROOT` environment variable
2. `D:/tools/spark`
3. `%USERPROFILE%/tools/spark`
4. `%USERPROFILE%/spark`
5. repo-local fallback `tools/vendor/spark`

If none of those paths exist, the tooling still points at `D:/tools/spark` as the expected external location.

## Splat asset layout

```text
static/splat_files/
  source/
  derived/
    <asset-id>/
  _pipeline/
```

- `source/`: raw input assets
- `derived/<asset-id>/`: generated manifests and `.rad/.radc` runtime files
- `_pipeline/`: auto-ingest status files

## Manifest format

Example:

```json
{
  "schema_version": 1,
  "asset_id": "object",
  "default_variant": "balanced",
  "variants": {
    "source": {
      "path": "source/object.ply",
      "format": "ply",
      "lod": false,
      "paged": false
    },
    "balanced": {
      "path": "derived/object/object-balanced-lod.rad",
      "format": "rad",
      "lod": true,
      "paged": true
    }
  }
}
```

Older manifests with flat relative paths are still supported by compatibility lookup.

## Viewer behavior

The React frontend asks the FastAPI backend to resolve assets in this order:

1. derived manifest for the asset id
2. selected manifest variant from the frontend quality selector
3. direct file fallback for legacy assets
4. generic `object` fallback

## Offline tooling

Use `tools/build_spark_assets.py` from the project root.

Register a raw source file:

```bash
python tools/build_spark_assets.py register-source static/splat_files/source/object.ply --asset-id object --set-default
```

Register an existing built variant:

```bash
python tools/build_spark_assets.py register-variant static/splat_files/derived/object/object-balanced-lod.rad --asset-id object --variant balanced --lod --paged --source static/splat_files/source/object.ply --set-default
```

Build a LoD variant from an external Spark checkout:

```bash
python tools/build_spark_assets.py build-lod static/splat_files/source/object.ply --asset-id object --variant balanced --spark-root D:/tools/spark --set-default --register-source
```

Sync the whole directory and auto-build the default runtime variant:

```bash
python tools/build_spark_assets.py sync --spark-root D:/tools/spark --variant balanced
```

## Automatic ingest flow

1. Put a new raw source asset into `static/splat_files/source/`
2. Refresh or start the FastAPI backend
3. The backend launches `tools/build_spark_assets.py sync` in the background
4. The pipeline registers `source`
5. The pipeline auto-builds the configured runtime variant, usually `balanced`
6. The viewer loads the generated manifest and `.rad` runtime asset

Legacy files dropped into `static/splat_files/` root are still detected and moved into `source/`.

## Environment requirements

`build-lod` depends on Spark's Rust-based toolchain:

- `node`
- `npm`
- `cargo`
- a local Spark checkout where `npm run build-lod` works

Relevant environment variables:

- `SPARK_ROOT`: local Spark checkout
- `SPARK_AUTO_INGEST`: enable or disable background sync
- `SPARK_AUTO_VARIANT`: default runtime variant to auto-build

## Recommended policy for very large assets

- `preview`: `quick`, `--max-sh=0`, chunked `.rad`
- `balanced`: `quality`, `--max-sh=1`, chunked `.rad`
- `full`: `quality`, `--max-sh=3`, chunked `.rad`

For very large assets, do not ship raw `.ply` files to the viewer. Build chunked `-lod.rad` files and keep `source` only for offline validation.

## Phase-field 3DGS (相场 3DGS)

相场(phase-field)3DGS 数据走严格子集:

- 只接受 `*_gaussian.ply`(`PHASEFIELD_3DGS_SUFFIX_PATTERN` 常量)。
- 跳过 `*_nonzero_points.ply` / `*.vtk` / `*.xyz`。
- 默认 variant = `full`(`max_sh=3`),manifest 写入 `default_variant: "full"`。
- Frontend 默认 `recommended_render_profile = "quality"`。

完整说明见 [`docs/PHASEFIELD_3DGS_UPGRADE.md`](PHASEFIELD_3DGS_UPGRADE.md)。

可以通过环境变量 `STRICT_PHASEFIELD_SOURCE=false` 关闭严格过滤,回到接受任意 `.ply` 的旧行为(用于非相场 3DGS 数据)。
