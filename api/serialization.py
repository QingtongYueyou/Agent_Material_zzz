from __future__ import annotations

import math
from typing import Any


def _json_safe(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        return None if math.isnan(value) or math.isinf(value) else value
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return str(value)


def _dataframe_records(df: Any, field_map: dict[str, str]) -> list[dict[str, Any]]:
    if df is None or not hasattr(df, "to_dict"):
        return []

    records = df.to_dict(orient="records")
    result: list[dict[str, Any]] = []
    for row in records:
        normalized: dict[str, Any] = {}
        for source_key, target_key in field_map.items():
            normalized[target_key] = _json_safe(row.get(source_key))
        result.append(normalized)
    return result


def serialize_viz(viz: Any) -> dict[str, Any] | None:
    if not isinstance(viz, dict) or not viz.get("filename"):
        return None

    return {
        "filename": _json_safe(viz.get("filename")),
        "cif_path": _json_safe(viz.get("cif_path")),
        "lattice": _dataframe_records(
            viz.get("lattice_df"),
            {
                "Parameter": "parameter",
                "Value": "value",
                "Unit": "unit",
            },
        ),
        "composition": _dataframe_records(
            viz.get("comp_df"),
            {
                "Element": "element",
                "Count": "count",
                "Fraction": "fraction",
            },
        ),
        "xrd": _dataframe_records(
            viz.get("xrd_df"),
            {
                "2Theta": "two_theta",
                "Intensity": "intensity",
                "HKL": "hkl",
            },
        ),
    }


def serialize_workflow_event(event: dict[str, Any]) -> dict[str, Any]:
    payload = dict(event)
    if payload.get("type") == "final":
        payload["viz"] = serialize_viz(payload.get("viz"))
    return _json_safe(payload)
