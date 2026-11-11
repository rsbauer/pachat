import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from auth import get_current_user
from admin import delete_user, list_users
from routes import router

test_app = FastAPI()
test_app.include_router(router)


class FakeCursor:
    def __init__(self, fetchone_values=None, fetchall_values=None):
        self.fetchone_values = list(fetchone_values or [])
        self.fetchall_values = list(fetchall_values or [])
        self.statements = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def execute(self, query, params=None):
        self.statements.append((query, params))

    def fetchone(self):
        return self.fetchone_values.pop(0)

    def fetchall(self):
        return self.fetchall_values.pop(0)


class FakeConnection:
    def __init__(self, cursor):
        self.fake_cursor = cursor

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def cursor(self):
        return self.fake_cursor


class AdminTests(unittest.TestCase):
    def test_regular_user_cannot_access_admin_api(self):
        async def current_user():
            return {"id": uuid4(), "role": "user"}

        test_app.dependency_overrides[get_current_user] = current_user
        try:
            response = TestClient(test_app).get("/api/admin/users")
        finally:
            test_app.dependency_overrides.clear()

        self.assertEqual(response.status_code, 403)

    def test_user_listing_returns_counts_and_storage_without_file_content(self):
        user_id = uuid4()
        cursor = FakeCursor(
            fetchall_values=[[(user_id, "person", "Person", "user", None, 2, 1, 1200)]]
        )

        with patch("admin.get_db_connection", return_value=FakeConnection(cursor)):
            users = list_users()

        self.assertEqual(users[0]["chat_count"], 2)
        self.assertEqual(users[0]["file_count"], 1)
        self.assertEqual(users[0]["storage_bytes"], 1200)
        query = cursor.statements[0][0]
        self.assertNotIn("content", query.lower())
        self.assertNotIn("stored_name", query.lower())

    def test_user_deletion_removes_document_rows_account_and_files(self):
        user_id = uuid4()
        cursor = FakeCursor(fetchone_values=[(user_id,), (user_id,)])
        with tempfile.TemporaryDirectory() as upload_dir:
            user_dir = Path(upload_dir) / str(user_id)
            user_dir.mkdir()
            (user_dir / "encrypted-file.pdf").write_bytes(b"ciphertext")

            with patch("admin.get_db_connection", return_value=FakeConnection(cursor)):
                deleted = delete_user(user_id, upload_dir)

            self.assertTrue(deleted)
            self.assertFalse(user_dir.exists())

        statements = [query for query, _params in cursor.statements]
        self.assertIn("DELETE FROM uploaded_documents WHERE user_id = %s", statements[1])
        self.assertIn("DELETE FROM app_users", statements[2])
        self.assertIn("RETURNING id", statements[2])


if __name__ == "__main__":
    unittest.main()