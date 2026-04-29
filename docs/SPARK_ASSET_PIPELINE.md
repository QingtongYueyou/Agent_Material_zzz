# Spark Asset Pipeline

This project now supports a manifest-first splat loading flow for the Streamlit viewer.

## Goals

- Keep raw `.ply` / `.spz` source files out of the hot path for large assets.
- Prefer prebuilt Spark `.rad` / `-lod.rad` variants.
- Make quality selection explicit through manifest variants instead of filename guessing.
- Preserve a `source` fallback for debugging or validation.

## Manifest file

Place a manifest next to your splat files in `static/splat_files/`:

- `mp-1661648_LiFePO4.manifest.json`
- `object.manifest.json`

Example:

```json
{
  "schema_version": 1,
  "asset_id": "object",
  "default_variant": "balanced",
  "variants": {
    "source": {
      "path": "object.ply",
      "format": "ply",
      "lod": false,
      "paged": false
    },
    "preview": {
      "path": "object-preview-lod.rad",
      "format": "rad",
      "lod": true,
      "paged": true
    },
    "balanced": {
      "path": "object-balanced-lod.rad",
      "format": "rad",
      "lod": true,
      "paged": true
    },
    "full": {
      "path": "object-full-lod.rad",
      "format": "rad",
      "lod": true,
      "paged": true
    }
  }
}
```

## Viewer behavior

The Streamlit viewer now resolves assets in this order:

1. `<asset-id>.manifest.json`
2. manifest variant chosen by the `3D Asset Quality` selector
3. direct filename fallback (`-lod.rad`, `.rad`, `.ply`, `.spz`, `.splat`, `.ksplat`)
4. generic `object` fallback

## Offline tooling

Use `tools/build_spark_assets.py` from the project root.

Register a raw source file:

```bash
python tools/build_spark_assets.py register-source static/splat_files/object.ply --asset-id object --set-default
```

Register an existing built variant:

```bash
python tools/build_spark_assets.py register-variant static/splat_files/object-balanced-lod.rad --asset-id object --variant balanced --lod --paged --source static/splat_files/object.ply --set-default
```

Build a LoD variant from a local Spark checkout:

```bash
python tools/build_spark_assets.py build-lod static/splat_files/object.ply --asset-id object --variant balanced --spark-root D:/path/to/spark --set-default --register-source
```

Sync the whole directory and auto-build the default runtime variant for any new or changed source files:

```bash
python tools/build_spark_assets.py sync --spark-root D:/path/to/spark --variant balanced
```

## Environment requirements

`build-lod` depends on Spark's Rust toolchain:

- `node`
- `npm`
- `cargo`
- a local Spark source checkout where `npm run build-lod` works

If `cargo` is not installed yet, you can still use `register-source` and `register-variant` to wire manifests first.

## Drop-in flow

The app now supports an automatic ingest path:

1. Put a new source asset into `static/splat_files/`
2. Keep the filename aligned with your material key, for example `mp-1661648_LiFePO4.ply`
3. Start or refresh the Streamlit app
4. The app launches `tools/build_spark_assets.py sync` in the background
5. The pipeline registers the `source` variant and auto-builds the configured runtime variant, currently `balanced`
6. The viewer picks up the generated manifest and loads the built `.rad` asset instead of the raw `.ply`

Relevant environment variables:

- `SPARK_ROOT`: local Spark checkout used for `build-lod`
- `SPARK_AUTO_INGEST`: enable or disable background directory sync
- `SPARK_AUTO_VARIANT`: runtime variant built automatically for new assets

## Recommended variant policy for very large assets

- `preview`: `quick`, `--max-sh=0`, chunked `.rad`
- `balanced`: `quality`, `--max-sh=1`, chunked `.rad`
- `full`: `quality`, `--max-sh=3`, chunked `.rad`

The build script now auto-clamps `max_sh` to the source file's detected SH degree for `.ply` inputs. For example, if the source only contains DC terms (`sh_degree=0`), `balanced` and `full` will automatically fall back to `--max-sh=0` instead of failing the Spark build.

For `7-8GB` source assets, do not ship raw `.ply` to the viewer. Build chunked `-lod.rad` files and keep `source` only for offline validation.
