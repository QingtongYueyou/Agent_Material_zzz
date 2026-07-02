from __future__ import annotations

import base64
import json

import pytest

from core import upload_store


@pytest.fixture()
def isolated_upload_store(tmp_path, monkeypatch):
    monkeypatch.setattr(upload_store, "MCP_UPLOAD_DIR", tmp_path)
    monkeypatch.setattr(upload_store, "MCP_ALLOWED_UPLOAD_EXTENSIONS", {".txt", ".cif", ".xlsx"})
    monkeypatch.setattr(upload_store, "MCP_MAX_UPLOAD_MB", 1)
    return tmp_path


def test_save_upload_file_writes_metadata_and_base64(isolated_upload_store) -> None:
    metadata = upload_store.save_upload_file(
        "dos.txt",
        b"energy dos",
        mime_type="text/plain",
    )

    assert upload_store.FILE_ID_RE.fullmatch(metadata["file_id"])
    assert metadata["filename"] == "dos.txt"
    assert metadata["extension"] == ".txt"
    assert metadata["mime_type"] == "text/plain"
    assert metadata["size_bytes"] == len(b"energy dos")

    loaded = upload_store.get_file_metadata(metadata["file_id"])
    path = upload_store.resolve_file_path(metadata["file_id"])
    loaded_again, encoded = upload_store.read_file_base64(metadata["file_id"])

    assert loaded == loaded_again
    assert path.read_bytes() == b"energy dos"
    assert base64.b64decode(encoded.encode("ascii")) == b"energy dos"


def test_save_upload_file_rejects_path_filename(isolated_upload_store) -> None:
    with pytest.raises(upload_store.UploadValidationError, match="path separators"):
        upload_store.save_upload_file("../dos.txt", b"data")


def test_save_upload_file_rejects_disallowed_extension(isolated_upload_store) -> None:
    with pytest.raises(upload_store.UploadValidationError, match="not allowed"):
        upload_store.save_upload_file("paper.pdf", b"data")


def test_resolve_file_path_rejects_metadata_path_escape(isolated_upload_store) -> None:
    metadata = upload_store.save_upload_file("safe.txt", b"data")
    metadata_path = isolated_upload_store / metadata["file_id"] / upload_store.METADATA_FILENAME
    payload = json.loads(metadata_path.read_text(encoding="utf-8"))
    payload["stored_filename"] = "../evil.txt"
    metadata_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(upload_store.UploadValidationError, match="stored_filename"):
        upload_store.resolve_file_path(metadata["file_id"])


def test_get_file_metadata_rejects_invalid_file_id(isolated_upload_store) -> None:
    with pytest.raises(upload_store.UploadValidationError, match="Invalid file_id"):
        upload_store.get_file_metadata("../file_20260701_bad")


def test_register_existing_file_copies_into_upload_root(isolated_upload_store, tmp_path) -> None:
    source_path = tmp_path / "generated.cif"
    source_path.write_text("data_generated", encoding="utf-8")

    metadata = upload_store.register_existing_file(source_path, source="system_generated")
    stored_path = upload_store.resolve_file_path(metadata["file_id"])

    assert metadata["source"] == "system_generated"
    assert metadata["original_filename"] == "generated.cif"
    assert stored_path.read_text(encoding="utf-8") == "data_generated"
    assert isolated_upload_store.resolve() in stored_path.resolve().parents
