from __future__ import annotations

import importlib
import sys
import types
import unittest

from fastapi import FastAPI
from fastapi.testclient import TestClient


class ApiFilesTests(unittest.TestCase):
    def setUp(self) -> None:
        upload_store = types.ModuleType("core.upload_store")

        def save_upload_file(
            filename: str,
            content: bytes,
            mime_type: str | None = None,
            source: str = "user_upload",
        ) -> dict[str, object]:
            return {
                "file_id": "file_test",
                "filename": filename,
                "extension": ".txt",
                "mime_type": mime_type,
                "size_bytes": len(content),
                "sha256": "abc123",
                "created_at": 1.0,
                "source": source,
            }

        upload_store.save_upload_file = save_upload_file
        sys.modules["core.upload_store"] = upload_store

    def test_upload_endpoint_returns_file_metadata(self) -> None:
        files_api = importlib.import_module("api.files")
        app = FastAPI()
        app.include_router(files_api.router)
        client = TestClient(app)

        response = client.post(
            "/api/files/upload",
            files={"file": ("dos.txt", b"dos-data", "text/plain")},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "file_id": "file_test",
                "filename": "dos.txt",
                "extension": ".txt",
                "mime_type": "text/plain",
                "size_bytes": 8,
                "sha256": "abc123",
                "created_at": 1.0,
                "source": "user_upload",
            },
        )


if __name__ == "__main__":
    unittest.main()
