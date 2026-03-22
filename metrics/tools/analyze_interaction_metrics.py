from __future__ import annotations

import csv
import math
from collections import defaultdict
from pathlib import Path
from statistics import mean, median

from config.settings import INTERACTION_METRICS_FILE


def _to_float(value: str) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _percentile(sorted_values: list[float], p: float) -> float:
    if not sorted_values:
        return math.nan
    if len(sorted_values) == 1:
        return sorted_values[0]

    rank = (len(sorted_values) - 1) * p
    lower = math.floor(rank)
    upper = math.ceil(rank)
    if lower == upper:
        return sorted_values[lower]
    weight = rank - lower
    return sorted_values[lower] * (1 - weight) + sorted_values[upper] * weight


def load_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []

    with path.open("r", encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def summarize(rows: list[dict[str, str]]) -> list[dict[str, object]]:
    grouped: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        key = (row.get("model_name", "UNKNOWN"), row.get("interaction_type", "UNKNOWN"))
        grouped[key].append(row)

    summary = []
    for (model_name, interaction_type), items in sorted(grouped.items()):
        timings = [
            value
            for value in (_to_float(item.get("input_to_camera_change_ms", "")) for item in items)
            if value is not None
        ]
        timings.sort()

        summary.append(
            {
                "model_name": model_name,
                "interaction_type": interaction_type,
                "samples": len(timings),
                "vertex_count": items[-1].get("vertex_count", ""),
                "avg_ms": round(mean(timings), 3) if timings else math.nan,
                "median_ms": round(median(timings), 3) if timings else math.nan,
                "p90_ms": round(_percentile(timings, 0.9), 3) if timings else math.nan,
                "min_ms": round(min(timings), 3) if timings else math.nan,
                "max_ms": round(max(timings), 3) if timings else math.nan,
            }
        )

    return summary


def main() -> int:
    rows = load_rows(INTERACTION_METRICS_FILE)
    if not rows:
        print(f"No metrics found: {INTERACTION_METRICS_FILE}")
        return 0

    print(f"Metrics file: {INTERACTION_METRICS_FILE}")
    print(f"Total samples: {len(rows)}")
    print()

    for row in summarize(rows):
        print(f"Model: {row['model_name']}")
        print(f"  interaction: {row['interaction_type']}")
        print(f"  vertices: {row['vertex_count']}")
        print(f"  samples: {row['samples']}")
        print(f"  avg_ms: {row['avg_ms']}")
        print(f"  median_ms: {row['median_ms']}")
        print(f"  p90_ms: {row['p90_ms']}")
        print(f"  min_ms: {row['min_ms']}")
        print(f"  max_ms: {row['max_ms']}")
        print()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
