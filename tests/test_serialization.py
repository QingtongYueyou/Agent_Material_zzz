from __future__ import annotations

import math
import unittest

from api.serialization import _dataframe_records, _json_safe, serialize_workflow_event


class FakeDataFrame:
    def __init__(self, records: list[dict[str, object]]) -> None:
        self._records = records

    def to_dict(self, orient: str) -> list[dict[str, object]]:
        if orient != "records":
            raise AssertionError(f"unexpected orient: {orient}")
        return self._records


class SerializationTests(unittest.TestCase):
    def test_json_safe_normalizes_non_finite_and_nested_values(self) -> None:
        value = {
            "ok": 1,
            "nan": math.nan,
            "inf": math.inf,
            "items": (False, object()),
        }

        self.assertEqual(
            _json_safe(value),
            {"ok": 1, "nan": None, "inf": None, "items": [False, str(value["items"][1])]},
        )

    def test_dataframe_records_maps_fields_and_json_safes_values(self) -> None:
        df = FakeDataFrame(
            [
                {"Element": "Si", "Count": 2, "Fraction": 0.5, "Ignored": "x"},
                {"Element": "O", "Count": 4, "Fraction": math.nan},
            ]
        )

        records = _dataframe_records(
            df,
            {"Element": "element", "Count": "count", "Fraction": "fraction"},
        )

        self.assertEqual(
            records,
            [
                {"element": "Si", "count": 2, "fraction": 0.5},
                {"element": "O", "count": 4, "fraction": None},
            ],
        )

    def test_serialize_workflow_event_serializes_final_viz(self) -> None:
        event = {
            "type": "final",
            "viz": {
                "filename": "sample.cif",
                "cif_path": None,
                "lattice_df": FakeDataFrame([{"Parameter": "a", "Value": math.inf, "Unit": "A"}]),
                "comp_df": None,
                "xrd_df": None,
            },
        }

        payload = serialize_workflow_event(event)

        self.assertEqual(payload["viz"]["filename"], "sample.cif")
        self.assertEqual(payload["viz"]["lattice"], [{"parameter": "a", "value": None, "unit": "A"}])
        self.assertEqual(payload["viz"]["composition"], [])
        self.assertEqual(payload["viz"]["xrd"], [])


if __name__ == "__main__":
    unittest.main()
