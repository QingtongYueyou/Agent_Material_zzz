from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from core import processor


class FakeLattice:
    a = 1.0
    b = 2.0
    c = 3.0


class FakeComposition:
    def get_el_amt_dict(self) -> dict[str, int]:
        return {"Si": 1}

    def get_atomic_fraction(self, element: str) -> float:
        if element != "Si":
            raise AssertionError(f"unexpected element: {element}")
        return 1.0


class FakeStructure:
    lattice = FakeLattice()
    composition = FakeComposition()


class FakeXRDPattern:
    x = [10.0]
    y = [100.0]
    hkls = [[{"hkl": (1, 0, 0)}]]


class FakeXRDCalculator:
    def __init__(self, wavelength: str) -> None:
        self.wavelength = wavelength

    def get_pattern(self, structure: FakeStructure) -> FakeXRDPattern:
        return FakeXRDPattern()


class ProcessorTests(unittest.TestCase):
    def test_get_cif_info_uses_angstrom_unit_for_lattice(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cif_path = Path(tmp) / "sample.cif"
            cif_path.write_text("data_sample\n", encoding="utf-8")

            with (
                patch.object(processor, "HAS_PYMATGEN", True),
                patch.object(processor, "_load_structure", return_value=FakeStructure()),
                patch.object(processor, "XRDCalculator", FakeXRDCalculator, create=True),
            ):
                filename, lattice_df, comp_df, xrd_df = processor.get_cif_info(cif_path)

        self.assertEqual(filename, "sample.cif")
        self.assertEqual(lattice_df["Unit"].tolist(), ["Angstrom", "Angstrom", "Angstrom"])
        self.assertEqual(comp_df["Element"].tolist(), ["Si"])
        self.assertEqual(xrd_df["HKL"].tolist(), ["(1, 0, 0)"])


if __name__ == "__main__":
    unittest.main()
