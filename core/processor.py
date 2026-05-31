from __future__ import annotations

import glob
import logging
import os
from functools import lru_cache

import pandas as pd

from config.settings import BASE_DIR, CIF_DIR

try:
    from pymatgen.analysis.diffraction.xrd import XRDCalculator
    from pymatgen.core import Structure

    HAS_PYMATGEN = True
except ImportError:
    HAS_PYMATGEN = False

CURRENT_SCRIPT_DIR = str(BASE_DIR)
logger = logging.getLogger(__name__)


@lru_cache(maxsize=32)
def _load_structure(cif_path: str, mtime_ns: int, size: int):
    return Structure.from_file(cif_path)


def get_cif_info(cif_file: str | os.PathLike):
    """
    Parse a CIF file and return DataFrames used by the visualization layer.
    """
    if not HAS_PYMATGEN:
        return None, None, None, None

    cif_path = str(cif_file)
    try:
        stat = os.stat(cif_path)
    except OSError:
        return None, None, None, None

    filename = os.path.basename(cif_path)

    try:
        structure = _load_structure(cif_path, stat.st_mtime_ns, stat.st_size)
    except Exception:
        return None, None, None, None

    lattice = structure.lattice
    lattice_df = pd.DataFrame(
        {
            "Parameter": ["a", "b", "c"],
            "Value": [lattice.a, lattice.b, lattice.c],
            "Unit": ["Angstrom", "Angstrom", "Angstrom"],
        }
    )

    comp = structure.composition
    element_data = []
    for element, amount in comp.get_el_amt_dict().items():
        element_data.append(
            {
                "Element": element,
                "Count": amount,
                "Fraction": comp.get_atomic_fraction(element),
            }
        )

    comp_df = pd.DataFrame(element_data)

    try:
        xrd_calc = XRDCalculator(wavelength="CuKa")
        pattern = xrd_calc.get_pattern(structure)
        xrd_data = []
        for theta, intensity, hkls in zip(pattern.x, pattern.y, pattern.hkls):
            if theta > 70:
                break
            hkl_str = str(hkls[0]["hkl"])
            xrd_data.append({"2Theta": theta, "Intensity": intensity, "HKL": hkl_str})
        xrd_df = pd.DataFrame(xrd_data)
    except Exception:
        xrd_df = pd.DataFrame()

    return filename, lattice_df, comp_df, xrd_df


def get_latest_cif_info(cif_dir: str | os.PathLike = CIF_DIR):
    """
    Parse the newest CIF file in a directory for visualization.
    """
    cif_dir_str = str(cif_dir)
    logger.debug("Script directory: %s", CURRENT_SCRIPT_DIR)
    logger.debug("Scanning CIF directory: %s", cif_dir_str)

    if not HAS_PYMATGEN:
        logger.debug("pymatgen is unavailable; skipping CIF parsing.")
        return None, None, None, None

    search_pattern = os.path.join(cif_dir_str, "*.cif")
    list_of_files = glob.glob(search_pattern)

    logger.debug("Found CIF file count: %s", len(list_of_files))

    if not list_of_files:
        return None, None, None, None

    latest_file = max(list_of_files, key=os.path.getctime)
    filename = os.path.basename(latest_file)
    logger.debug("Selected newest CIF file: %s", filename)

    return get_cif_info(latest_file)
