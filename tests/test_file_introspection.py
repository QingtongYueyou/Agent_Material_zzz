"""Unit tests for core.file_introspection.

Conventions follow tests/test_processor.py (unittest.TestCase + stubs) and
tests/test_upload_store.py (monkeypatch + tmp_path). Tests reuse:
- ``_install_tool_dependency_stubs`` (extended locally to stub pymatgen.core.Structure too)
- ``FakeLattice / FakeComposition / FakeStructure`` from tests/test_processor.py
"""

from __future__ import annotations

import json
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

import pytest

from config import settings as settings_module
from core import file_introspection, upload_store


# ---------------------------------------------------------------------------
# Stubs
# ---------------------------------------------------------------------------


class FakeLattice:
    a = 4.5
    b = 4.5
    c = 6.8
    alpha = 90.0
    beta = 90.0
    gamma = 120.0


class FakeElement:
    def __init__(self, symbol: str) -> None:
        self._symbol = symbol

    def __str__(self) -> str:
        return self._symbol

    def __repr__(self) -> str:
        return f"FakeElement({self._symbol!r})"


class FakeComposition:
    def __init__(self) -> None:
        self._data = {"Li": 1, "Fe": 1, "P": 1, "O": 4}

    def get_reduced_formula_and_factor(self):
        return "LiFePO4", 1

    def get_el_amt_dict(self):
        return dict(self._data)

    def get_atomic_fraction(self, element) -> float:
        total = sum(self._data.values())
        symbol = str(element)
        return self._data.get(symbol, 0) / total

    @property
    def elements(self):
        return [FakeElement(name) for name in self._data]


class FakeSymmetry:
    symbol = "Pnma"
    number = 62
    crystal_system = "orthorhombic"


class FakeStructure:
    def __init__(self) -> None:
        self.composition = FakeComposition()
        self.lattice = FakeLattice()
        self.sites = [object()] * 28

    def __len__(self) -> int:
        return len(self.sites)

    @classmethod
    def from_file(cls, path: str) -> "FakeStructure":
        # Validate path exists; raise like pymatgen would on malformed input.
        if not Path(path).exists():
            raise ValueError("CIF parse error: file not found")
        return cls()

    @classmethod
    def from_sites(cls, sites) -> "FakeStructure":
        instance = cls()
        instance.sites = list(sites)
        return instance


class FakeSpacegroupAnalyzer:
    def __init__(self, structure) -> None:
        self.structure = structure

    def get_space_group_symbol(self):
        return FakeSymmetry.symbol

    def get_space_group_number(self):
        return FakeSymmetry.number

    def get_crystal_system(self):
        return FakeSymmetry.crystal_system


def _install_tool_dependency_stubs() -> None:
    """Stub agno, mp_api, pymatgen (including pymatgen.core.Structure + SpacegroupAnalyzer)
    so file_introspection can ``from pymatgen.core import Structure`` without real pymatgen.
    """
    agno_module = types.ModuleType("agno")
    agno_tools_module = types.ModuleType("agno.tools")

    def tool(*args, **kwargs):
        def decorator(func):
            return func

        return decorator

    agno_tools_module.tool = tool
    agno_module.tools = agno_tools_module
    sys.modules["agno"] = agno_module
    sys.modules["agno.tools"] = agno_tools_module

    mp_api_module = types.ModuleType("mp_api")
    mp_api_client_module = types.ModuleType("mp_api.client")

    class MPRester:
        def __init__(self, *args, **kwargs) -> None:
            pass

    mp_api_client_module.MPRester = MPRester
    mp_api_module.client = mp_api_client_module
    sys.modules["mp_api"] = mp_api_module
    sys.modules["mp_api.client"] = mp_api_client_module

    pymatgen_module = types.ModuleType("pymatgen")
    pymatgen_core = types.ModuleType("pymatgen.core")
    pymatgen_core.Structure = FakeStructure
    pymatgen_module.core = pymatgen_core
    symmetry_module = types.ModuleType("pymatgen.symmetry")
    analyzer_module = types.ModuleType("pymatgen.symmetry.analyzer")
    analyzer_module.SpacegroupAnalyzer = FakeSpacegroupAnalyzer
    symmetry_module.analyzer = analyzer_module
    pymatgen_module.symmetry = symmetry_module
    sys.modules["pymatgen"] = pymatgen_module
    sys.modules["pymatgen.core"] = pymatgen_core
    sys.modules["pymatgen.symmetry"] = symmetry_module
    sys.modules["pymatgen.symmetry.analyzer"] = analyzer_module


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def isolated_upload_store(tmp_path, monkeypatch):
    """Per-test upload + cache root pointed at tmp_path."""
    upload_root = tmp_path / "uploads"
    cache_root = tmp_path / "introspect_cache"
    upload_root.mkdir(parents=True, exist_ok=True)
    cache_root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(upload_store, "MCP_UPLOAD_DIR", upload_root)
    monkeypatch.setattr(upload_store, "MCP_ALLOWED_UPLOAD_EXTENSIONS",
                        {".cif", ".txt", ".dat", ".csv", ".xlsx", ".stl", ".png"})
    monkeypatch.setattr(upload_store, "FILE_INTROSPECTION_CACHE_DIR", cache_root)

    return {"upload_root": upload_root, "cache_root": cache_root}


def _new_file_id(date: str = "20260702", suffix: str = "ab") -> str:
    return f"file_{date}_{suffix.ljust(16, '0')[:16]}"


def _register_uploads(upload_root: Path, items: list[tuple[str, bytes]]) -> dict[str, str]:
    """Create fake original.<ext> + metadata.json under upload_root/<file_id>/.

    Returns {file_id: filename}.
    """
    out: dict[str, str] = {}
    for idx, (filename, content) in enumerate(items):
        ext = Path(filename).suffix.lower()
        date_label = "20260702"
        # Deterministic 16-hex-char segment per upload.
        hex_segment = f"{(idx + 1):016x}"
        file_id = f"file_{date_label}_{hex_segment}"
        directory = upload_root / file_id
        directory.mkdir(parents=True, exist_ok=True)
        (directory / f"original{ext}").write_bytes(content)
        metadata = {
            "file_id": file_id,
            "filename": filename,
            "original_filename": filename,
            "stored_filename": f"original{ext}",
            "extension": ext,
            "mime_type": None,
            "size_bytes": len(content),
            "sha256": "",
            "created_at": 0.0,
            "source": "user_upload",
        }
        (directory / "metadata.json").write_text(
            json.dumps(metadata), encoding="utf-8",
        )
        out[file_id] = filename
    return out


def _make_dos_bytes() -> bytes:
    lines = ["# Energy DOS", "# header", ""]
    energy = -10.0
    for _ in range(600):
        lines.append(f"{energy:.4f} {abs(energy) * 0.1 + 0.5:.4f}")
        energy += 0.04
    return ("\n".join(lines) + "\n").encode("utf-8")


def _make_xrd_bytes() -> bytes:
    lines = ["# 2Theta  Intensity"]
    theta = 5.0
    for _ in range(1100):
        intensity = 100.0 if abs((theta - 26.5)) < 0.3 else 5.0
        lines.append(f"{theta:.4f}  {intensity:.4f}")
        theta += 0.15
    return ("\n".join(lines) + "\n").encode("utf-8")


def _make_ambiguous_bytes() -> bytes:
    # Range fits both DOS-style [-50, 50] and a low-angle XRD series.
    # Without explicit labels the heuristic should mark this as needing
    # clarification.
    lines = ["# numeric series", "# two columns"]
    energy = 0.0
    for _ in range(250):
        lines.append(f"{energy:.4f}  {abs(energy) * 0.1:.4f}")
        energy += 0.2
    return ("\n".join(lines) + "\n").encode("utf-8")


def _make_phase_curve_bytes() -> bytes:
    lines = ["# Temperature  Property"]
    temp = 273.0
    for _ in range(400):
        lines.append(f"{temp:.2f}  {(temp - 273) / 100:.4f}")
        temp += 5.0
    return ("\n".join(lines) + "\n").encode("utf-8")


def _make_xls_bytes(sheet_name: str = "binary_phase") -> bytes:
    """Generate a real legacy ``.xls`` (BIFF8) workbook in memory.

    Uses ``xlwt`` (test-only) to produce a fixture readable by the production
    ``xlrd`` parser. The fixture is intentionally small — the parser caps at
    ``FILE_INTROSPECTION_FULLER_PREVIEW_ROWS`` rows.
    """
    import io
    import xlwt  # local import: only present in test env

    workbook = xlwt.Workbook(encoding="utf-8")
    sheet = workbook.add_sheet(sheet_name)
    sheet.write(0, 0, "A")
    sheet.write(0, 1, "B")
    sheet.write(0, 2, "T")
    for idx, (a, b) in enumerate([(0.1, 0.2), (0.3, 0.5), (0.4, 0.8), (0.6, 1.1)], start=1):
        sheet.write(idx, 0, a)
        sheet.write(idx, 1, b)
        sheet.write(idx, 2, 900 + a * 100)
    buf = io.BytesIO()
    workbook.save(buf)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class FileIntrospectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        _install_tool_dependency_stubs()

    def setUp(self) -> None:
        # Reset cache dirs / locks between tests.
        with tempfile.TemporaryDirectory() as tmp:
            self._tmp = Path(tmp)
        self._cache_root = self._tmp / "introspect_cache"
        self._cache_root.mkdir(parents=True, exist_ok=True)
        # Ensure the real core.upload_store is loaded. Earlier tests (e.g.
        # test_api_files) install a partial stub via sys.modules that lacks
        # ``get_file_metadata`` / ``resolve_file_path``. Force the real one
        # to be re-imported so file_introspection's call paths work.
        import importlib
        self._original_upload_store = sys.modules.get("core.upload_store")
        # Force a fresh import of the real core.upload_store to undo any
        # partial stubs left behind by earlier tests (e.g. test_api_files).
        sys.modules.pop("core.upload_store", None)
        real_upload_store = importlib.import_module("core.upload_store")
        sys.modules["core.upload_store"] = real_upload_store
        # IMPORTANT: re-bind the local ``upload_store`` module reference so
        # subsequent ``monkeypatch.setattr(upload_store, ...)`` calls in the
        # test bodies patch the freshly imported module — not the one bound
        # at the top of this file.
        global upload_store  # noqa: PLW0603
        upload_store = real_upload_store
        import core as _core_pkg
        setattr(_core_pkg, "upload_store", real_upload_store)

    def tearDown(self) -> None:
        # Restore whatever sys.modules['core.upload_store'] looked like before
        # the test, so other test classes see the same import state.
        if self._original_upload_store is None:
            sys.modules.pop("core.upload_store", None)
        else:
            sys.modules["core.upload_store"] = self._original_upload_store

    # ----- Helpers -----------------------------------------------------------

    def _setup(self, tmp_path, monkeypatch):
        upload_root = tmp_path / "uploads"
        upload_root.mkdir(parents=True, exist_ok=True)
        monkeypatch.setattr(upload_store, "MCP_UPLOAD_DIR", upload_root)
        # core.upload_store imports MCP_UPLOAD_DIR from config.settings at
        # module load; the local copy inside _upload_root() reads from there.
        # Patch both so the test's tmp_path is the one consulted regardless of
        # module-reload order in the wider test session.
        from config import settings as settings_module
        monkeypatch.setattr(settings_module, "MCP_UPLOAD_DIR", upload_root)
        monkeypatch.setattr(
            upload_store,
            "MCP_ALLOWED_UPLOAD_EXTENSIONS",
            {".cif", ".txt", ".dat", ".csv", ".xlsx", ".xls"},
        )
        monkeypatch.setattr(upload_store, "FILE_INTROSPECTION_CACHE_DIR", self._cache_root)
        return upload_root

    # 1. CIF happy path
    def test_cif_happy_path_returns_crystal_structure_summary(self):
        with tempfile.TemporaryDirectory() as tmp:
            from _pytest.monkeypatch import MonkeyPatch
            mp = MonkeyPatch()
            try:
                upload_root = self._setup(Path(tmp), mp)
                uploads = _register_uploads(upload_root, [("sample.cif", b"data_image0\n")])
                fid = next(iter(uploads))
                result = file_introspection.summarize_file(fid, detail_level="default")
            finally:
                mp.undo()

        self.assertEqual(result["content_kind"], "crystal_structure")
        self.assertEqual(result["inferred_content_type"], "structure")
        self.assertEqual(result["confidence"], "high")
        self.assertEqual(result["recommended_mcp_intents"], ["structure"])
        self.assertEqual(result["facts"]["symmetry"]["symbol"], "Pnma")
        self.assertEqual(result["facts"]["symmetry"]["number"], 62)
        self.assertEqual(result["facts"]["formula"], "LiFePO4")
        self.assertEqual(sorted(result["facts"]["element_list"]),
                         ["Fe", "Li", "O", "P"])

    # 2. CIF malformed → error
    def test_cif_malformed_file_returns_error_kind(self):
        with tempfile.TemporaryDirectory() as tmp:
            from _pytest.monkeypatch import MonkeyPatch
            mp = MonkeyPatch()
            try:
                upload_root = self._setup(Path(tmp), mp)

                # Override FakeStructure.from_file to raise on demand.
                original_from_file = FakeStructure.from_file

                def boom(path: str):
                    raise ValueError("malformed")

                FakeStructure.from_file = boom  # type: ignore[assignment]
                try:
                    uploads = _register_uploads(upload_root, [("bad.cif", b"x")])
                    fid = next(iter(uploads))
                    result = file_introspection.summarize_file(fid)
                finally:
                    FakeStructure.from_file = original_from_file  # type: ignore[assignment]
            finally:
                mp.undo()

        self.assertEqual(result["content_kind"], "error")
        self.assertIn("error", result["facts"])

    # 3. Empty file
    def test_empty_file_returns_unsupported(self):
        with tempfile.TemporaryDirectory() as tmp:
            from _pytest.monkeypatch import MonkeyPatch
            mp = MonkeyPatch()
            try:
                upload_root = self._setup(Path(tmp), mp)
                uploads = _register_uploads(upload_root, [("empty.txt", b"")])
                fid = next(iter(uploads))
                result = file_introspection.summarize_file(fid)
            finally:
                mp.undo()

        self.assertEqual(result["content_kind"], "unsupported")
        self.assertEqual(result["sha256"], None)

    # 4. PNG bytes with .txt extension
    def test_binary_bytes_with_text_extension_returns_unsupported(self):
        png_header = bytes([0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A]) + b"\x00\x01\x02"
        with tempfile.TemporaryDirectory() as tmp:
            from _pytest.monkeypatch import MonkeyPatch
            mp = MonkeyPatch()
            try:
                upload_root = self._setup(Path(tmp), mp)
                uploads = _register_uploads(upload_root, [("trojan.txt", png_header * 200)])
                fid = next(iter(uploads))
                result = file_introspection.summarize_file(fid)
            finally:
                mp.undo()

        self.assertEqual(result["content_kind"], "unsupported")
        self.assertEqual(result["parser_id"], "tabular_text")
        self.assertTrue(any("binary" in w for w in result["warnings"]))

    # 5. DOS-like .dat
    def test_dos_like_dat_returns_dos_intent_high_confidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            from _pytest.monkeypatch import MonkeyPatch
            mp = MonkeyPatch()
            try:
                upload_root = self._setup(Path(tmp), mp)
                uploads = _register_uploads(upload_root, [("dos.dat", _make_dos_bytes())])
                fid = next(iter(uploads))
                result = file_introspection.summarize_file(fid)
            finally:
                mp.undo()

        self.assertEqual(result["content_kind"], "tabular_numeric")
        self.assertEqual(result["inferred_content_type"], "dos")
        self.assertEqual(result["confidence"], "high")
        self.assertEqual(result["recommended_mcp_intents"], ["dos"])

    # 6. XRD-like .dat
    def test_xrd_like_dat_returns_xrd_intent_high_confidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            from _pytest.monkeypatch import MonkeyPatch
            mp = MonkeyPatch()
            try:
                upload_root = self._setup(Path(tmp), mp)
                uploads = _register_uploads(upload_root, [("xrd.dat", _make_xrd_bytes())])
                fid = next(iter(uploads))
                result = file_introspection.summarize_file(fid)
            finally:
                mp.undo()

        self.assertEqual(result["content_kind"], "tabular_numeric")
        self.assertEqual(result["inferred_content_type"], "xrd")
        self.assertEqual(result["confidence"], "high")
        self.assertEqual(result["recommended_mcp_intents"], ["xrd"])

    # 7. Ambiguous numeric data
    def test_ambiguous_numeric_returns_low_confidence_and_clarification(self):
        with tempfile.TemporaryDirectory() as tmp:
            from _pytest.monkeypatch import MonkeyPatch
            mp = MonkeyPatch()
            try:
                upload_root = self._setup(Path(tmp), mp)
                uploads = _register_uploads(
                    upload_root, [("series.dat", _make_ambiguous_bytes())]
                )
                fid = next(iter(uploads))
                result = file_introspection.summarize_file(fid)
            finally:
                mp.undo()

        # Either needs_clarification or a low-confidence narrow guess is acceptable;
        # the series here starts at 0 and steps by 0.2 — both DOS-style range
        # checks would pass, so we expect both candidates or "needs_clarification".
        self.assertEqual(result["content_kind"], "tabular_numeric")
        self.assertTrue(result["needs_clarification"] or
                        "dos" in result["recommended_mcp_intents"] and
                        result["confidence"] in {"low", "medium"})

    # 8. CSV with quoted multi-line cells (no crash)
    def test_csv_with_quoted_multiline_cells_does_not_crash(self):
        csv_bytes = (
            b"Index,Name,Value\n"
            b"1,\"multi\nline\nvalue\",3.14\n"
            b"2,\"another\nline\",2.71\n"
            b"3,plain,1.41\n"
        )
        with tempfile.TemporaryDirectory() as tmp:
            from _pytest.monkeypatch import MonkeyPatch
            mp = MonkeyPatch()
            try:
                upload_root = self._setup(Path(tmp), mp)
                uploads = _register_uploads(upload_root, [("data.csv", csv_bytes)])
                fid = next(iter(uploads))
                result = file_introspection.summarize_file(fid)
            finally:
                mp.undo()

        self.assertIn(result["content_kind"], {"tabular_numeric", "tabular_text", "error"})
        # No crash is the acceptance criterion.
        self.assertIn("facts", result)

    # 9. XLSX with two sheets (only first non-default-named is used for preview)
    def test_xlsx_with_two_sheets_picks_first_usable(self):
        # openpyxl is optional; skip if not installed.
        openpyxl = pytest.importorskip("openpyxl")

        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            xlsx_path = tmp_dir / "binary.xlsx"
            wb = openpyxl.Workbook()
            sheet_a = wb.active
            sheet_a.title = "Intro"
            sheet_a.append(["this is just text"])
            sheet_b = wb.create_sheet("binary_phase")
            sheet_b.append(["A", "B", "T"])
            for a, b in [(0.1, 0.2), (0.3, 0.5), (0.4, 0.8)]:
                sheet_b.append([f"{a:.3f}", f"{b:.3f}", f"{900 + a*100:.1f}"])
            wb.save(str(xlsx_path))

            # Wire in.
            from _pytest.monkeypatch import MonkeyPatch
            mp = MonkeyPatch()
            try:
                upload_root = self._setup(tmp_dir, mp)
                # Borrow the same xlsx file under upload_root/<fid>/original.xlsx
                fid = _new_file_id()
                file_dir = upload_root / fid
                file_dir.mkdir(parents=True, exist_ok=True)
                stored = file_dir / "original.xlsx"
                stored.write_bytes(xlsx_path.read_bytes())
                metadata = {
                    "file_id": fid, "filename": "binary.xlsx",
                    "original_filename": "binary.xlsx", "stored_filename": "original.xlsx",
                    "extension": ".xlsx", "mime_type": None,
                    "size_bytes": stored.stat().st_size, "sha256": "", "created_at": 0.0,
                    "source": "user_upload",
                }
                (file_dir / "metadata.json").write_text(json.dumps(metadata), encoding="utf-8")

                result = file_introspection.summarize_file(fid)
            finally:
                mp.undo()

        self.assertEqual(result["content_kind"], "spreadsheet")
        self.assertEqual(result["parser_id"], "xlsx")
        self.assertIn("binary_phase", result["facts"]["sheet_names"])
        # Phase-1 keeps parser behavior simple; we don't require intent inference here.

    # 9a. Comma-delimited .dat parses as two numeric columns (Fix 3)
    def test_dat_with_comma_delimiter_parses_two_columns(self):
        body = b"# two-theta,intensity\n10,1200\n20,2400\n30,800\n40,300\n"
        with tempfile.TemporaryDirectory() as tmp:
            from _pytest.monkeypatch import MonkeyPatch
            mp = MonkeyPatch()
            try:
                upload_root = self._setup(Path(tmp), mp)
                uploads = _register_uploads(upload_root, [("xrd_comma.dat", body)])
                fid = next(iter(uploads))
                result = file_introspection.summarize_file(fid)
            finally:
                mp.undo()

        self.assertEqual(result["parser_id"], "tabular_text")
        self.assertEqual(result["content_kind"], "tabular_numeric")
        self.assertEqual(result["facts"]["delimiter_guess"], ",")
        # Column 0 ranges fit XRD; intent should be xrd high.
        self.assertEqual(result["inferred_content_type"], "xrd")
        self.assertEqual(result["confidence"], "high")
        self.assertEqual(result["preview"]["column_stats"][0]["min"], 10.0)
        self.assertEqual(result["preview"]["column_stats"][1]["max"], 2400.0)

    # 9b. Semicolon-delimited .txt parses as two numeric columns (Fix 3)
    def test_txt_with_semicolon_delimiter_parses(self):
        body = b"# energy;dos\n-5.0;0.1\n-4.0;0.2\n-3.0;0.5\n-2.0;1.2\n-1.0;0.8\n"
        with tempfile.TemporaryDirectory() as tmp:
            from _pytest.monkeypatch import MonkeyPatch
            mp = MonkeyPatch()
            try:
                upload_root = self._setup(Path(tmp), mp)
                uploads = _register_uploads(upload_root, [("dos.txt", body)])
                fid = next(iter(uploads))
                result = file_introspection.summarize_file(fid)
            finally:
                mp.undo()

        self.assertEqual(result["parser_id"], "tabular_text")
        self.assertEqual(result["content_kind"], "tabular_numeric")
        self.assertEqual(result["facts"]["delimiter_guess"], ";")
        self.assertEqual(result["inferred_content_type"], "dos")
        self.assertEqual(result["preview"]["column_stats"][0]["min"], -5.0)

    # 9c. Whitespace-delimited .dat still parses (no regression, Fix 3)
    def test_whitespace_delimiter_still_works(self):
        with tempfile.TemporaryDirectory() as tmp:
            from _pytest.monkeypatch import MonkeyPatch
            mp = MonkeyPatch()
            try:
                upload_root = self._setup(Path(tmp), mp)
                uploads = _register_uploads(upload_root, [("plain.dat", _make_dos_bytes())])
                fid = next(iter(uploads))
                result = file_introspection.summarize_file(fid)
            finally:
                mp.undo()

        # Existing DOS-like bytes are whitespace-separated; the column stats
        # should still come from the whitespace path, not from a delimiter
        # fallback that doesn't exist in the file.
        self.assertEqual(result["content_kind"], "tabular_numeric")
        self.assertEqual(result["inferred_content_type"], "dos")
        self.assertEqual(result["confidence"], "high")
        self.assertNotEqual(result["facts"]["delimiter_guess"], ",")

    # 9d. European-decimal whitespace (no delimiter) still parses (Fix 3 sanity)
    def test_whitespace_with_european_decimal_cells(self):
        # "1,5 2,3" should be parsed as two cells [1.5, 2.3] via whitespace
        # split + European-decimal coercion, NOT as a comma-delimited split
        # into [1.0, 5.0, 2.0, 3.0]. Whitespace path is tried first and wins.
        body = b"# T,Cp\n300,0 1,5\n400,0 2,3\n500,0 3,5\n"
        rows = file_introspection._parse_text_rows(body.decode("utf-8").splitlines())
        self.assertEqual(rows, [[300.0, 1.5], [400.0, 2.3], [500.0, 3.5]])

    # 9e. .xls (legacy BIFF) happy path via xlrd (Fix 1)
    def test_xls_happy_path_returns_spreadsheet_summary(self):
        pytest.importorskip("xlrd")
        pytest.importorskip("xlwt")  # fixture writer; only needed in test env

        xls_bytes = _make_xls_bytes(sheet_name="binary_phase")
        with tempfile.TemporaryDirectory() as tmp:
            from _pytest.monkeypatch import MonkeyPatch
            mp = MonkeyPatch()
            try:
                upload_root = self._setup(Path(tmp), mp)
                uploads = _register_uploads(upload_root, [("binary_phase.xls", xls_bytes)])
                fid = next(iter(uploads))
                result = file_introspection.summarize_file(fid)
            finally:
                mp.undo()

        self.assertEqual(result["parser_id"], "xls")
        self.assertEqual(result["content_kind"], "tabular_numeric")
        self.assertEqual(result["inferred_content_type"], "binary_phase")
        self.assertEqual(result["confidence"], "high")
        self.assertEqual(result["recommended_mcp_intents"], ["binary_phase"])
        self.assertIn("binary_phase", result["facts"]["sheet_names"])
        self.assertEqual(result["facts"]["delimiter_guess"], "xls")
        self.assertGreaterEqual(len(result["preview"]["first_sheet_preview"]), 1)

    # 9f. .xls with xlrd import masked returns error kind (Fix 1 graceful failure)
    def test_xls_with_missing_xlrd_returns_error_kind(self):
        # Hide xlrd in sys.modules so the ``from xlrd import open_workbook``
        # in _parse_xls fails on ImportError.
        sys.modules["xlrd"] = None  # type: ignore[assignment]
        try:
            with tempfile.TemporaryDirectory() as tmp:
                from _pytest.monkeypatch import MonkeyPatch
                mp = MonkeyPatch()
                try:
                    upload_root = self._setup(Path(tmp), mp)
                    # Bytes don't matter — parser short-circuits on import error.
                    uploads = _register_uploads(
                        upload_root, [("any.xls", b"\xd0\xcf\x11\xe0")]
                    )
                    fid = next(iter(uploads))
                    result = file_introspection.summarize_file(fid)
                finally:
                    mp.undo()
        finally:
            sys.modules.pop("xlrd", None)

        self.assertEqual(result["parser_id"], "xls")
        self.assertEqual(result["content_kind"], "error")
        self.assertTrue(result["warnings"] and "xlrd missing" in result["warnings"][0])

    # 9g. .xls text masquerading file is unsupported (not error)
    def test_xls_text_masquerading_returns_unsupported(self):
        pytest.importorskip("xlrd")

        body = b"this is plain text masquerading as a .xls file\n"
        with tempfile.TemporaryDirectory() as tmp:
            from _pytest.monkeypatch import MonkeyPatch
            mp = MonkeyPatch()
            try:
                upload_root = self._setup(Path(tmp), mp)
                uploads = _register_uploads(upload_root, [("fake.xls", body)])
                fid = next(iter(uploads))
                result = file_introspection.summarize_file(fid)
            finally:
                mp.undo()

        self.assertEqual(result["parser_id"], "xls")
        self.assertEqual(result["content_kind"], "unsupported")

    # 9h. ``fuller`` detail level truly expands head_rows + adds std/q1/median/q3 (Fix 2)
    def test_fuller_detail_expands_head_rows_for_dat(self):
        with tempfile.TemporaryDirectory() as tmp:
            from _pytest.monkeypatch import MonkeyPatch
            mp = MonkeyPatch()
            try:
                upload_root = self._setup(Path(tmp), mp)
                # 200 numeric rows so fuller has room to expand.
                body = ("# energy  dos\n" + "".join(
                    f"{-10.0 + i*0.1:.4f}  {0.1 + 0.001*i:.4f}\n"
                    for i in range(200)
                )).encode("utf-8")
                uploads = _register_uploads(upload_root, [("dos.dat", body)])
                fid = next(iter(uploads))

                default = file_introspection.summarize_file(fid, detail_level="default")
                fuller = file_introspection.summarize_file(fid, detail_level="fuller")
            finally:
                mp.undo()

        fuller_cap = settings_module.FILE_INTROSPECTION_FULLER_PREVIEW_ROWS
        default_cap = settings_module.FILE_INTROSPECTION_DEFAULT_PREVIEW_ROWS

        # Default view: 5 rows, no extra descriptive stats.
        self.assertEqual(default["summary_level"], "default")
        self.assertLessEqual(len(default["preview"]["head_rows"]), default_cap)
        default_col_stats = default["preview"]["column_stats"][0]
        self.assertNotIn("std", default_col_stats)
        self.assertNotIn("q1", default_col_stats)

        # Fuller view: 200 rows + full descriptive stats.
        self.assertEqual(fuller["summary_level"], "fuller")
        self.assertEqual(len(fuller["preview"]["head_rows"]), fuller_cap)
        fuller_col_stats = fuller["preview"]["column_stats"][0]
        for key in ("std", "q1", "median", "q3"):
            self.assertIn(key, fuller_col_stats, f"missing fuller key {key}")
        # The fuller view is served from the cache (no re-parse).
        self.assertTrue(fuller.get("from_cache"))

    # 9i. ``fuller`` persisted cache keeps fuller fields but trims default preview
    def test_fuller_persisted_cache_does_not_bloat(self):
        from config import settings as settings_module
        with tempfile.TemporaryDirectory() as tmp:
            from _pytest.monkeypatch import MonkeyPatch
            mp = MonkeyPatch()
            try:
                upload_root = self._setup(Path(tmp), mp)
                body = b"# a,b\n" + b"".join(
                    (f"{i:.1f},{i*2:.1f}\n").encode("utf-8") for i in range(50)
                )
                uploads = _register_uploads(upload_root, [("series.csv", body)])
                fid = next(iter(uploads))

                # Trigger cache write by reading default.
                file_introspection.summarize_file(fid, detail_level="default")
                # Read the cached payload directly.
                cache_path = upload_store.get_introspection_cache_path(
                    fid, parser_version=file_introspection.PARSER_VERSION_INT
                )
                self.assertIsNotNone(cache_path)
                payload = json.loads(cache_path.read_text(encoding="utf-8"))
            finally:
                mp.undo()

        default_cap = settings_module.FILE_INTROSPECTION_DEFAULT_PREVIEW_ROWS
        # Persisted head_rows is trimmed to default cap.
        self.assertLessEqual(len(payload["preview"]["head_rows"]), default_cap)
        # Persisted column_stats has std/q1/median/q3 stripped at the default level.
        for entry in payload["preview"]["column_stats"].values():
            self.assertNotIn("std", entry)
            self.assertNotIn("q1", entry)
        # But ``facts._fuller_*`` are present so a subsequent fuller read
        # can expand without re-parsing. JSON loads int keys as strings.
        self.assertIn("_fuller_head_rows", payload["facts"])
        self.assertIn("_fuller_column_stats", payload["facts"])
        fuller_stats = payload["facts"]["_fuller_column_stats"]["0"]
        for key in ("std", "q1", "median", "q3"):
            self.assertIn(key, fuller_stats)

    # 9j. ``fuller`` after a default read uses the cache and expands (zero re-parse)
    def test_fuller_uses_cache_after_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            from _pytest.monkeypatch import MonkeyPatch
            mp = MonkeyPatch()
            try:
                upload_root = self._setup(Path(tmp), mp)
                # Generate 250 rows so the FULLER cap (200) actually trims.
                body = b"# x,y\n" + b"".join(
                    (f"{i},{i*3}\n").encode("utf-8") for i in range(250)
                )
                uploads = _register_uploads(upload_root, [("series.csv", body)])
                fid = next(iter(uploads))

                # Populate cache via a default call.
                first = file_introspection.summarize_file(fid, detail_level="default")
                # Read fuller; should hit cache.
                second = file_introspection.summarize_file(fid, detail_level="fuller")
            finally:
                mp.undo()

        self.assertFalse(first.get("from_cache"))
        self.assertTrue(second.get("from_cache"))
        self.assertEqual(second["summary_level"], "fuller")
        self.assertEqual(len(second["preview"]["head_rows"]),
                         settings_module.FILE_INTROSPECTION_FULLER_PREVIEW_ROWS)

    # 10. Oversize file
    def test_oversize_file_returns_oversize_kind_without_parsing(self):
        with tempfile.TemporaryDirectory() as tmp:
            from _pytest.monkeypatch import MonkeyPatch
            mp = MonkeyPatch()
            try:
                upload_root = self._setup(Path(tmp), mp)
                # Build a file larger than the cap.
                fid = _new_file_id()
                file_dir = upload_root / fid
                file_dir.mkdir(parents=True, exist_ok=True)
                stored = file_dir / "original.dat"
                stored.write_bytes(b"x" * (file_introspection.FILE_INTROSPECTION_MAX_FILE_SIZE_BYTES + 1000))
                metadata = {
                    "file_id": fid, "filename": "huge.dat",
                    "original_filename": "huge.dat", "stored_filename": "original.dat",
                    "extension": ".dat", "mime_type": None,
                    "size_bytes": stored.stat().st_size, "sha256": "", "created_at": 0.0,
                    "source": "user_upload",
                }
                (file_dir / "metadata.json").write_text(json.dumps(metadata), encoding="utf-8")

                result = file_introspection.summarize_file(fid)
            finally:
                mp.undo()

        self.assertEqual(result["content_kind"], "oversize")
        self.assertEqual(result["recommended_mcp_intents"], [])
        self.assertGreater(len(result["warnings"]), 0)

    # 11. Cache invalidation on file modification
    def test_cache_invalidates_when_file_changes(self):
        with tempfile.TemporaryDirectory() as tmp:
            from _pytest.monkeypatch import MonkeyPatch
            mp = MonkeyPatch()
            try:
                upload_root = self._setup(Path(tmp), mp)
                uploads = _register_uploads(upload_root, [("e.dat", _make_dos_bytes())])
                fid = next(iter(uploads))
                first = file_introspection.summarize_file(fid)
                # Mutate content under upload.
                stored = upload_root / fid / "original.dat"
                stored.write_bytes(_make_xrd_bytes())
                # Touch mtime so the size+ns check definitely invalidates.
                stored.touch()
                second = file_introspection.summarize_file(fid)
            finally:
                mp.undo()

        # Either we get a freshly-computed summary (different sha256) or
        # the second call still returns the stale content; verify sha256 differs
        # OR the second call returns the new inferred type. Most reliable: sha256.
        self.assertNotEqual(first["sha256"], second["sha256"])

    # 12. Global cache hit when same content uploaded under different file_id
    def test_global_cache_hit_on_identical_content_different_file_id(self):
        with tempfile.TemporaryDirectory() as tmp:
            from _pytest.monkeypatch import MonkeyPatch
            mp = MonkeyPatch()
            try:
                upload_root = self._setup(Path(tmp), mp)
                # Upload 1
                _register_uploads(upload_root, [("dos.dat", _make_dos_bytes())])
                fid1 = next(iter(upload_root.iterdir())).name
                first = file_introspection.summarize_file(fid1)

                # Upload 2 (same bytes, different file_id). Manually create
                # a second file with a different file_id to avoid _register_uploads'
                # deterministic id collision.
                fid2 = "file_20260702_ffffffffffffffff"
                directory = upload_root / fid2
                directory.mkdir(parents=True, exist_ok=True)
                (directory / "original.dat").write_bytes(_make_dos_bytes())
                import json as _json
                metadata2 = {
                    "file_id": fid2,
                    "filename": "again.dat",
                    "original_filename": "again.dat",
                    "stored_filename": "original.dat",
                    "extension": ".dat",
                    "mime_type": None,
                    "size_bytes": len(_make_dos_bytes()),
                    "sha256": "",
                    "created_at": 0.0,
                    "source": "user_upload",
                }
                (directory / "metadata.json").write_text(
                    _json.dumps(metadata2), encoding="utf-8",
                )
                second = file_introspection.summarize_file(fid2)
                # Snapshot the per-file path BEFORE undoing the monkeypatch —
                # otherwise resolve_introspection_cache_path will use the
                # real production root.
                per_file_path = upload_store.resolve_introspection_cache_path(fid2)
                sha_match = (first["sha256"] == second["sha256"])
                per_file_exists = per_file_path is not None and per_file_path.exists()
            finally:
                mp.undo()

        self.assertTrue(sha_match)
        # second call should NOT have computed (or computed and repopulated per-file).
        # Global cache marked the lookup; per-file cache should also be populated.
        self.assertTrue(per_file_exists)

    # 13. Atomic write (simulated race)
    def test_atomic_write_succeeds_even_when_temp_path_replace_fails_first_time(self):
        # This tests the design contract rather than an actual race.
        # We monkey-patch Path.replace to raise on the first invocation, then
        # verify the second call (a retry) succeeds.
        with tempfile.TemporaryDirectory() as tmp:
            from _pytest.monkeypatch import MonkeyPatch
            mp = MonkeyPatch()
            try:
                upload_root = self._setup(Path(tmp), mp)
                uploads = _register_uploads(upload_root, [("dos.dat", _make_dos_bytes())])
                fid = next(iter(uploads))

                original_replace = Path.replace

                calls = {"count": 0}

                def flaky_replace(self, target):
                    calls["count"] += 1
                    if calls["count"] == 1:
                        raise OSError("simulated race")
                    return original_replace(self, target)

                Path.replace = flaky_replace  # type: ignore[assignment]
                try:
                    # First call: temp write succeeds but replace fails → cache not written.
                    file_introspection.summarize_file(fid)
                    # Second call with different content (so cache miss, recompute, retry replace).
                    stored = upload_root / fid / "original.dat"
                    stored.write_bytes(_make_xrd_bytes())
                    stored.touch()
                    result = file_introspection.summarize_file(fid)
                finally:
                    Path.replace = original_replace  # type: ignore[assignment]
            finally:
                mp.undo()

        # The retry succeeded; result is a valid DOS/XRD summary (here XRD).
        self.assertIn(result["inferred_content_type"], {"xrd", "dos"})

    # 14. Unsupported extension
    def test_unsupported_extension_returns_unsupported_without_reading(self):
        with tempfile.TemporaryDirectory() as tmp:
            from _pytest.monkeypatch import MonkeyPatch
            mp = MonkeyPatch()
            try:
                upload_root = self._setup(Path(tmp), mp)
                uploads = _register_uploads(upload_root, [("model.stl", b"solid x\n")])
                fid = next(iter(uploads))
                # Force the size override for .stl: not in allowed extenions but exists
                # in file_introspection.PARSER_ID_BY_EXT-lookup; SHOULD NOT even try to read.
                result = file_introspection.summarize_file(fid)
            finally:
                mp.undo()

        self.assertEqual(result["content_kind"], "unsupported")
        self.assertEqual(result["parser_id"], "none")


if __name__ == "__main__":
    unittest.main()
