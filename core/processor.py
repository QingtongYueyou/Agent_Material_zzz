from __future__ import annotations

import glob
import os

import pandas as pd

from config.settings import BASE_DIR, CIF_DIR

try:
    from pymatgen.core import Structure
    from pymatgen.analysis.diffraction.xrd import XRDCalculator

    HAS_PYMATGEN = True
except ImportError:
    HAS_PYMATGEN = False

CURRENT_SCRIPT_DIR = str(BASE_DIR)


def get_latest_cif_info(cif_dir: str | os.PathLike = CIF_DIR):
    """
    获取目录下最新的 CIF 文件，解析结构并返回用于绘图的 DataFrame。
    """
    cif_dir_str = str(cif_dir)
    print("-" * 50)
    print(f"DEBUG: 脚本所在位置: {CURRENT_SCRIPT_DIR}")
    print(f"DEBUG: 正在扫描目标: {cif_dir_str}")

    if not HAS_PYMATGEN:
        print("DEBUG: 缺少 pymatgen")
        return None, None, None, None

    search_pattern = os.path.join(cif_dir_str, "*.cif")
    list_of_files = glob.glob(search_pattern)

    print(f"DEBUG: 找到文件数量: {len(list_of_files)}")

    if not list_of_files:
        return None, None, None, None

    latest_file = max(list_of_files, key=os.path.getctime)
    filename = os.path.basename(latest_file)
    print(f"DEBUG: 成功锁定最新文件: {filename}")

    try:
        structure = Structure.from_file(latest_file)
    except Exception as e:
        print(f"DEBUG: 文件解析失败: {e}")
        return None, None, None, None

    lattice = structure.lattice
    lattice_df = pd.DataFrame(
        {
            "Parameter": ["a", "b", "c"],
            "Value": [lattice.a, lattice.b, lattice.c],
            "Unit": ["Å", "Å", "Å"],
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
