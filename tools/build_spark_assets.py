from __future__ import annotations

import argparse
import json
import math
import os
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_SPLAT_DIR = ROOT_DIR / "static" / "splat_files"
DEFAULT_SPARK_ROOT = ROOT_DIR / "tools" / "vendor" / "spark"
STATUS_FILE_NAME = ".spark_asset_pipeline_status.json"
RAW_SOURCE_SUFFIXES = {".ply", ".spz", ".splat", ".ksplat"}
BUILDABLE_SOURCE_SUFFIXES = {".ply", ".spz"}

VARIANT_PROFILES = {
    "preview": {"method": "quick", "max_sh": 0, "chunked": True},
    "balanced": {"method": "quality", "max_sh": 1, "chunked": True},
    "full": {"method": "quality", "max_sh": 3, "chunked": True},
}


def _timestamp_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ensure_local_toolchain_path() -> None:
    cargo_bin = Path.home() / ".cargo" / "bin"
    if cargo_bin.exists():
        current_path = os.environ.get("PATH", "")
        cargo_str = str(cargo_bin)
        if cargo_str.lower() not in current_path.lower():
            os.environ["PATH"] = f"{cargo_str}{os.pathsep}{current_path}"


def _detect_format(path: Path) -> str:
    return path.suffix.lower().lstrip(".")


def _read_ply_header_lines(path: Path) -> list[str]:
    if path.suffix.lower() != ".ply" or not path.exists():
        return []

    header_lines: list[str] = []
    with path.open("rb") as fh:
        for raw_line in fh:
            line = raw_line.decode("ascii", errors="ignore").strip()
            header_lines.append(line)
            if line == "end_header":
                break

    return header_lines


def _get_ply_vertex_count(path: Path) -> int | None:
    for line in _read_ply_header_lines(path):
        if line.startswith("element vertex "):
            try:
                return int(line.split()[-1])
            except ValueError:
                return None

    return None


def _get_ply_sh_degree(path: Path) -> int | None:
    header_lines = _read_ply_header_lines(path)
    if not header_lines:
        return None

    rest_property_count = 0
    for line in header_lines:
        if line.startswith("property ") and " f_rest_" in line:
            rest_property_count += 1

    if rest_property_count == 0:
        return 0

    if rest_property_count % 3 != 0:
        return None

    coeffs_per_channel = (rest_property_count // 3) + 1
    coeffs_sqrt = math.isqrt(coeffs_per_channel)
    if coeffs_sqrt * coeffs_sqrt != coeffs_per_channel or coeffs_sqrt == 0:
        return None

    return coeffs_sqrt - 1


def _relative_to_splat_dir(path: Path, splat_dir: Path) -> str:
    return path.resolve().relative_to(splat_dir.resolve()).as_posix()


def _load_manifest(manifest_path: Path, asset_id: str) -> dict:
    if manifest_path.exists():
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            data.setdefault("schema_version", 1)
            data.setdefault("asset_id", asset_id)
            data.setdefault("variants", {})
            return data

    return {
        "schema_version": 1,
        "asset_id": asset_id,
        "default_variant": "",
        "variants": {},
    }


def _save_manifest(manifest_path: Path, manifest: dict) -> None:
    manifest["updated_at_utc"] = _timestamp_utc()
    manifest_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _ensure_command(name: str) -> None:
    if shutil.which(name) is None:
        raise RuntimeError(f"Required command not found on PATH: {name}")


def _save_json(path: Path, payload: dict) -> None:
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _npm_executable() -> str:
    npm_name = "npm.cmd" if os.name == "nt" else "npm"
    if shutil.which(npm_name):
        return npm_name
    return "npm"


def _status_file_path(splat_dir: Path) -> Path:
    return splat_dir / STATUS_FILE_NAME


def _save_status_file(path: Path, payload: dict) -> None:
    payload["updated_at_utc"] = _timestamp_utc()
    _save_json(path, payload)


def _is_source_candidate(path: Path) -> bool:
    if not path.is_file():
        return False

    suffix = path.suffix.lower()
    if suffix not in RAW_SOURCE_SUFFIXES:
        return False

    lower_stem = path.stem.lower()
    return not lower_stem.endswith("-lod")


def _iter_source_candidates(splat_dir: Path) -> list[Path]:
    return sorted(path for path in splat_dir.iterdir() if _is_source_candidate(path))


def _resolve_manifest_entry_path(manifest_path: Path, raw_path: str) -> Path | None:
    candidate = Path(raw_path)
    resolved = candidate if candidate.is_absolute() else (manifest_path.parent / candidate).resolve()
    if resolved.exists():
        return resolved
    return None


def _variant_output_path(manifest_path: Path, variant_name: str) -> Path | None:
    manifest = _read_manifest(manifest_path)
    if not manifest:
        return None

    variants = manifest.get("variants")
    if not isinstance(variants, dict):
        return None

    payload = variants.get(variant_name)
    if not isinstance(payload, dict):
        return None

    raw_path = payload.get("path") or payload.get("file") or payload.get("relative_path")
    if not isinstance(raw_path, str) or not raw_path.strip():
        return None

    return _resolve_manifest_entry_path(manifest_path, raw_path)


def _read_manifest(path: Path) -> dict | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None

    if isinstance(data, dict):
        return data
    return None


def _source_variant_matches(manifest_path: Path, source_path: Path) -> bool:
    variant_path = _variant_output_path(manifest_path, "source")
    if variant_path is None:
        return False

    try:
        return variant_path.resolve() == source_path.resolve()
    except OSError:
        return False


def _variant_is_current(manifest_path: Path, source_path: Path, variant_name: str) -> bool:
    variant_path = _variant_output_path(manifest_path, variant_name)
    if variant_path is None or not variant_path.exists():
        return False

    manifest = _read_manifest(manifest_path) or {}
    if str(manifest.get("default_variant") or "").strip() != variant_name:
        return False

    try:
        return source_path.stat().st_mtime <= variant_path.stat().st_mtime
    except OSError:
        return False


def _variant_entry(
    *,
    asset_file: Path,
    variant_name: str,
    splat_dir: Path,
    lod: bool,
    paged: bool,
    source_path: Path | None = None,
    build_info: dict | None = None,
    bundle_size_bytes: int | None = None,
) -> dict:
    header_file_size_bytes = asset_file.stat().st_size
    effective_file_size_bytes = bundle_size_bytes if bundle_size_bytes is not None else header_file_size_bytes
    entry = {
        "path": _relative_to_splat_dir(asset_file, splat_dir),
        "format": _detect_format(asset_file),
        "lod": lod,
        "paged": paged,
        "file_size_bytes": effective_file_size_bytes,
        "registered_at_utc": _timestamp_utc(),
    }

    vertex_count = _get_ply_vertex_count(asset_file)
    if vertex_count is not None:
        entry["vertex_count"] = vertex_count
    sh_degree = _get_ply_sh_degree(asset_file)
    if sh_degree is not None:
        entry["sh_degree"] = sh_degree

    if bundle_size_bytes is not None:
        entry["header_file_size_bytes"] = header_file_size_bytes
        entry["bundle_size_bytes"] = bundle_size_bytes

    if source_path is not None:
        entry["source_path"] = _relative_to_splat_dir(source_path, splat_dir)
        source_vertex_count = _get_ply_vertex_count(source_path)
        if source_vertex_count is not None:
            entry["source_vertex_count"] = source_vertex_count
        source_sh_degree = _get_ply_sh_degree(source_path)
        if source_sh_degree is not None:
            entry["source_sh_degree"] = source_sh_degree

    if build_info:
        entry["build"] = build_info

    return entry


def _register_variant(
    *,
    manifest_path: Path,
    asset_id: str,
    variant_name: str,
    asset_file: Path,
    splat_dir: Path,
    lod: bool,
    paged: bool,
    source_path: Path | None = None,
    build_info: dict | None = None,
    set_default: bool = False,
    bundle_size_bytes: int | None = None,
) -> None:
    manifest = _load_manifest(manifest_path, asset_id)
    manifest["variants"][variant_name] = _variant_entry(
        asset_file=asset_file,
        variant_name=variant_name,
        splat_dir=splat_dir,
        lod=lod,
        paged=paged,
        source_path=source_path,
        build_info=build_info,
        bundle_size_bytes=bundle_size_bytes,
    )

    if source_path is not None:
        manifest["source"] = {
            "path": _relative_to_splat_dir(source_path, splat_dir),
            "format": _detect_format(source_path),
            "file_size_bytes": source_path.stat().st_size,
        }
        source_vertex_count = _get_ply_vertex_count(source_path)
        if source_vertex_count is not None:
            manifest["source"]["vertex_count"] = source_vertex_count
        source_sh_degree = _get_ply_sh_degree(source_path)
        if source_sh_degree is not None:
            manifest["source"]["sh_degree"] = source_sh_degree

    if set_default or not manifest.get("default_variant"):
        manifest["default_variant"] = variant_name

    _save_manifest(manifest_path, manifest)


def _rename_chunked_outputs(source_prefix: str, target_prefix: str, directory: Path) -> list[Path]:
    moved_paths: list[Path] = []
    for path in sorted(directory.glob(f"{source_prefix}*")):
        target_name = path.name.replace(source_prefix, target_prefix, 1)
        target_path = directory / target_name
        if target_path.exists():
            target_path.unlink()
        path.replace(target_path)
        moved_paths.append(target_path)
    return moved_paths


def _build_lod_variant(args: argparse.Namespace) -> None:
    input_path = Path(args.input).resolve()
    if not input_path.exists():
        raise FileNotFoundError(f"Input file not found: {input_path}")

    splat_dir = Path(args.splat_dir).resolve()
    manifest_path = Path(args.manifest).resolve() if args.manifest else splat_dir / f"{args.asset_id}.manifest.json"
    spark_root = Path(args.spark_root).resolve()

    _ensure_command(_npm_executable())
    _ensure_command("cargo")

    if not spark_root.exists():
        raise FileNotFoundError(f"Spark checkout not found: {spark_root}")

    profile = VARIANT_PROFILES.get(args.variant, {})
    method = args.method or profile.get("method", "quality")
    chunked = args.chunked if args.chunked is not None else profile.get("chunked", True)
    requested_max_sh = args.max_sh if args.max_sh is not None else profile.get("max_sh")
    source_sh_degree = _get_ply_sh_degree(input_path)
    max_sh = requested_max_sh
    if (
        max_sh is not None
        and source_sh_degree is not None
        and max_sh > source_sh_degree
    ):
        print(
            f"Requested max_sh={max_sh} exceeds source sh_degree={source_sh_degree}; "
            f"clamping to {source_sh_degree}."
        )
        max_sh = source_sh_degree

    command = [_npm_executable(), "run", "build-lod", "--", str(input_path)]
    command.append("--quality" if method == "quality" else "--quick")
    if max_sh is not None:
        command.append(f"--max-sh={max_sh}")
    if chunked:
        command.append("--rad-chunked")

    subprocess.run(command, cwd=spark_root, check=True)

    source_prefix = f"{input_path.stem}-lod"
    target_prefix = f"{args.asset_id}-{args.variant}-lod"
    moved_paths = _rename_chunked_outputs(source_prefix, target_prefix, input_path.parent)

    target_header = input_path.parent / f"{target_prefix}.rad"
    if target_header not in moved_paths or not target_header.exists():
        raise FileNotFoundError(
            f"Expected build output not found after rename: {target_header}"
        )

    bundle_size_bytes = sum(path.stat().st_size for path in moved_paths)
    build_info = {
        "builder": "spark-build-lod",
        "method": method,
        "chunked": chunked,
        "source_sh_degree": source_sh_degree,
        "requested_max_sh": requested_max_sh,
        "effective_max_sh": max_sh,
        "spark_root": str(spark_root),
        "header_file_size_bytes": target_header.stat().st_size,
        "bundle_size_bytes": bundle_size_bytes,
        "output_files": [path.name for path in moved_paths],
    }
    _register_variant(
        manifest_path=manifest_path,
        asset_id=args.asset_id,
        variant_name=args.variant,
        asset_file=target_header,
        splat_dir=splat_dir,
        lod=True,
        paged=chunked,
        source_path=input_path,
        build_info=build_info,
        set_default=args.set_default,
        bundle_size_bytes=bundle_size_bytes,
    )

    if args.register_source:
        _register_variant(
            manifest_path=manifest_path,
            asset_id=args.asset_id,
            variant_name="source",
            asset_file=input_path,
            splat_dir=splat_dir,
            lod=False,
            paged=False,
            source_path=input_path,
            set_default=False,
        )

    print(f"Built Spark LoD variant '{args.variant}'")
    print(f"Manifest: {manifest_path}")
    print(f"Header:   {target_header}")


def _register_existing_variant(args: argparse.Namespace) -> None:
    asset_file = Path(args.file).resolve()
    if not asset_file.exists():
        raise FileNotFoundError(f"Variant file not found: {asset_file}")

    splat_dir = Path(args.splat_dir).resolve()
    manifest_path = Path(args.manifest).resolve() if args.manifest else splat_dir / f"{args.asset_id}.manifest.json"
    source_path = Path(args.source).resolve() if args.source else None
    bundle_size_bytes = None
    if args.paged and asset_file.suffix.lower() == ".rad":
        radc_files = sorted(asset_file.parent.glob(f"{asset_file.stem}-*.radc"))
        if radc_files:
            bundle_size_bytes = asset_file.stat().st_size + sum(
                path.stat().st_size for path in radc_files
            )

    _register_variant(
        manifest_path=manifest_path,
        asset_id=args.asset_id,
        variant_name=args.variant,
        asset_file=asset_file,
        splat_dir=splat_dir,
        lod=args.lod,
        paged=args.paged,
        source_path=source_path,
        set_default=args.set_default,
        bundle_size_bytes=bundle_size_bytes,
    )

    print(f"Registered variant '{args.variant}'")
    print(f"Manifest: {manifest_path}")


def _register_source_variant(args: argparse.Namespace) -> None:
    source_file = Path(args.input).resolve()
    if not source_file.exists():
        raise FileNotFoundError(f"Source file not found: {source_file}")

    splat_dir = Path(args.splat_dir).resolve()
    manifest_path = Path(args.manifest).resolve() if args.manifest else splat_dir / f"{args.asset_id}.manifest.json"

    _register_variant(
        manifest_path=manifest_path,
        asset_id=args.asset_id,
        variant_name="source",
        asset_file=source_file,
        splat_dir=splat_dir,
        lod=False,
        paged=False,
        source_path=source_file,
        set_default=args.set_default,
    )

    print("Registered source variant")
    print(f"Manifest: {manifest_path}")


def _sync_splat_dir(args: argparse.Namespace) -> None:
    splat_dir = Path(args.splat_dir).resolve()
    spark_root = Path(args.spark_root).resolve() if args.spark_root else None
    can_build = spark_root is not None and spark_root.exists()
    status_path = _status_file_path(splat_dir)
    status: dict[str, object] = {
        "schema_version": 1,
        "running": True,
        "variant": args.variant,
        "spark_root": str(spark_root) if spark_root is not None else "",
        "started_at_utc": _timestamp_utc(),
        "assets": {},
        "summary": {
            "source_count": 0,
            "built": 0,
            "registered": 0,
            "up_to_date": 0,
            "pending_build": 0,
            "errors": 0,
        },
    }
    _save_status_file(status_path, status)

    source_files = _iter_source_candidates(splat_dir)
    summary = status["summary"]
    if isinstance(summary, dict):
        summary["source_count"] = len(source_files)

    try:
        for source_path in source_files:
            asset_id = source_path.stem
            manifest_path = splat_dir / f"{asset_id}.manifest.json"
            buildable = source_path.suffix.lower() in BUILDABLE_SOURCE_SUFFIXES
            needs_source_registration = (
                not manifest_path.exists()
                or not _source_variant_matches(manifest_path, source_path)
            )
            needs_variant_build = (
                buildable
                and can_build
                and not _variant_is_current(manifest_path, source_path, args.variant)
            )

            status_asset = {
                "source_file": source_path.name,
                "source_mtime": int(source_path.stat().st_mtime),
                "buildable": buildable,
                "variant": args.variant,
                "state": "scanning",
                "message": "",
                "updated_at_utc": _timestamp_utc(),
            }
            assets_payload = status.get("assets")
            if isinstance(assets_payload, dict):
                assets_payload[asset_id] = status_asset
            _save_status_file(status_path, status)

            try:
                if needs_variant_build:
                    status_asset["state"] = "building"
                    status_asset["message"] = f"Building {args.variant} variant"
                    status_asset["updated_at_utc"] = _timestamp_utc()
                    _save_status_file(status_path, status)

                    build_args = argparse.Namespace(
                        input=str(source_path),
                        asset_id=asset_id,
                        variant=args.variant,
                        spark_root=str(spark_root),
                        manifest=str(manifest_path),
                        splat_dir=str(splat_dir),
                        method=None,
                        max_sh=None,
                        chunked=None,
                        set_default=True,
                        register_source=True,
                    )
                    _build_lod_variant(build_args)
                    status_asset["state"] = "built"
                    status_asset["message"] = f"Built {args.variant} variant"
                    if isinstance(summary, dict):
                        summary["built"] = int(summary.get("built", 0)) + 1
                elif needs_source_registration:
                    register_args = argparse.Namespace(
                        input=str(source_path),
                        asset_id=asset_id,
                        manifest=str(manifest_path),
                        splat_dir=str(splat_dir),
                        set_default=not _variant_is_current(manifest_path, source_path, args.variant),
                    )
                    _register_source_variant(register_args)
                    status_asset["state"] = "registered"
                    status_asset["message"] = "Registered source variant"
                    if isinstance(summary, dict):
                        summary["registered"] = int(summary.get("registered", 0)) + 1
                elif buildable and not can_build:
                    status_asset["state"] = "pending_build"
                    status_asset["message"] = "Spark root unavailable; source file left as-is"
                    if isinstance(summary, dict):
                        summary["pending_build"] = int(summary.get("pending_build", 0)) + 1
                else:
                    status_asset["state"] = "up_to_date"
                    status_asset["message"] = "Asset already up to date"
                    if isinstance(summary, dict):
                        summary["up_to_date"] = int(summary.get("up_to_date", 0)) + 1
            except Exception as exc:  # noqa: BLE001
                status_asset["state"] = "error"
                status_asset["message"] = str(exc)
                if isinstance(summary, dict):
                    summary["errors"] = int(summary.get("errors", 0)) + 1

            status_asset["updated_at_utc"] = _timestamp_utc()
            _save_status_file(status_path, status)
    finally:
        status["running"] = False
        status["finished_at_utc"] = _timestamp_utc()
        _save_status_file(status_path, status)

    print(f"Synced {len(source_files)} source asset(s)")
    print(f"Status:   {status_path}")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build and register Spark splat assets and manifest files."
    )
    parser.add_argument(
        "--splat-dir",
        default=str(DEFAULT_SPLAT_DIR),
        help="Directory that stores frontend splat assets.",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    register_source = subparsers.add_parser(
        "register-source",
        help="Create or update a manifest that points at an existing source splat file.",
    )
    register_source.add_argument("input", help="Source splat file (.ply/.spz/.splat/...)")
    register_source.add_argument("--asset-id", required=True, help="Logical asset identifier.")
    register_source.add_argument("--manifest", help="Override manifest output path.")
    register_source.add_argument(
        "--set-default",
        action="store_true",
        help="Set the source variant as default.",
    )
    register_source.set_defaults(handler=_register_source_variant)

    register_variant = subparsers.add_parser(
        "register-variant",
        help="Register an existing preview/balanced/full asset file into a manifest.",
    )
    register_variant.add_argument("file", help="Built asset file to register.")
    register_variant.add_argument("--asset-id", required=True, help="Logical asset identifier.")
    register_variant.add_argument("--variant", required=True, help="Variant name, e.g. preview/balanced/full.")
    register_variant.add_argument("--manifest", help="Override manifest output path.")
    register_variant.add_argument("--source", help="Original source splat file.")
    register_variant.add_argument("--lod", action="store_true", help="Mark variant as LoD-enabled.")
    register_variant.add_argument("--paged", action="store_true", help="Mark variant as paged/streamed.")
    register_variant.add_argument("--set-default", action="store_true", help="Set this variant as default.")
    register_variant.set_defaults(handler=_register_existing_variant)

    build_lod = subparsers.add_parser(
        "build-lod",
        help="Run Spark's build-lod command, rename outputs, and register the variant in a manifest.",
    )
    build_lod.add_argument("input", help="Source splat file to convert.")
    build_lod.add_argument("--asset-id", required=True, help="Logical asset identifier.")
    build_lod.add_argument("--variant", required=True, help="Variant name, e.g. preview/balanced/full.")
    build_lod.add_argument(
        "--spark-root",
        required=True,
        help="Path to a local Spark source checkout where npm run build-lod can execute.",
    )
    build_lod.add_argument("--manifest", help="Override manifest output path.")
    build_lod.add_argument(
        "--method",
        choices=["quick", "quality"],
        help="Override the Spark LoD build method.",
    )
    build_lod.add_argument(
        "--max-sh",
        type=int,
        choices=[0, 1, 2, 3],
        help="Override the maximum spherical harmonics level.",
    )
    build_lod.add_argument(
        "--chunked",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Enable or disable --rad-chunked output.",
    )
    build_lod.add_argument(
        "--set-default",
        action="store_true",
        help="Set this built variant as default.",
    )
    build_lod.add_argument(
        "--register-source",
        action="store_true",
        help="Also register the input file as the 'source' variant.",
    )
    build_lod.set_defaults(handler=_build_lod_variant)

    sync_assets = subparsers.add_parser(
        "sync",
        help="Scan the splat directory, register new source files, and auto-build the preferred variant when needed.",
    )
    sync_assets.add_argument(
        "--spark-root",
        default=str(DEFAULT_SPARK_ROOT),
        help="Optional local Spark source checkout. When available, buildable sources are converted automatically.",
    )
    sync_assets.add_argument(
        "--variant",
        default="balanced",
        help="Variant name to auto-build for new or changed assets.",
    )
    sync_assets.set_defaults(handler=_sync_splat_dir)

    return parser


def main() -> int:
    _ensure_local_toolchain_path()
    parser = _build_parser()
    args = parser.parse_args()

    try:
        args.handler(args)
    except Exception as exc:  # noqa: BLE001
        parser.exit(1, f"Error: {exc}\n")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
