import stat
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4
from unittest.mock import patch

from cryptography.fernet import Fernet

from intake import encrypt_existing_documents, get_user_document, store_documents


class FakeCursor:
    def __init__(self, rows=None, row=None, fail_update=False):
        self.rows = rows or []
        self.row = row
        self.fail_update = fail_update
        self.statements = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def execute(self, query, params=None):
        self.statements.append((query, params))
        if self.fail_update and query.startswith("UPDATE"):
            raise RuntimeError("simulated database failure")

    def fetchall(self):
        return self.rows

    def fetchone(self):
        return self.row


class FakeConnection:
    def __init__(self, cursor):
        self.fake_cursor = cursor

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def cursor(self):
        return self.fake_cursor


class FileEncryptionTests(unittest.TestCase):
    def setUp(self):
        self.key = Fernet.generate_key().decode("ascii")
        self.cipher = Fernet(self.key.encode("ascii"))

    def test_existing_plaintext_file_is_migrated_and_permissions_restricted(self):
        user_id = uuid4()
        document_id = uuid4()
        original = b"private patient document"
        with TemporaryDirectory() as upload_dir:
            user_dir = Path(upload_dir) / str(user_id)
            user_dir.mkdir()
            document_path = user_dir / "document.txt"
            document_path.write_bytes(original)
            cursor = FakeCursor(rows=[(document_id, user_id, document_path.name)])

            with patch("intake.get_db_connection", return_value=FakeConnection(cursor)):
                migrated = encrypt_existing_documents(upload_dir, self.key)

            encrypted = document_path.read_bytes()
            self.assertEqual(migrated, 1)
            self.assertNotEqual(encrypted, original)
            self.assertEqual(self.cipher.decrypt(encrypted), original)
            self.assertEqual(stat.S_IMODE(document_path.stat().st_mode), 0o600)
            self.assertTrue(any("is_encrypted = TRUE" in query for query, _params in cursor.statements))

    def test_interrupted_migration_can_resume_without_double_encryption(self):
        user_id = uuid4()
        document_id = uuid4()
        original = b"resume-safe content"
        with TemporaryDirectory() as upload_dir:
            user_dir = Path(upload_dir) / str(user_id)
            user_dir.mkdir()
            document_path = user_dir / "document.txt"
            document_path.write_bytes(original)
            row = (document_id, user_id, document_path.name)
            failing_cursor = FakeCursor(rows=[row], fail_update=True)

            with patch("intake.get_db_connection", return_value=FakeConnection(failing_cursor)):
                with self.assertRaises(RuntimeError):
                    encrypt_existing_documents(upload_dir, self.key)

            first_encrypted_value = document_path.read_bytes()
            self.assertEqual(self.cipher.decrypt(first_encrypted_value), original)
            cursor = FakeCursor(rows=[row])
            with patch("intake.get_db_connection", return_value=FakeConnection(cursor)):
                migrated = encrypt_existing_documents(upload_dir, self.key)

            self.assertEqual(migrated, 1)
            self.assertEqual(document_path.read_bytes(), first_encrypted_value)
            self.assertEqual(self.cipher.decrypt(document_path.read_bytes()), original)

    def test_on_demand_read_decrypts_in_memory_without_changing_disk(self):
        user_id = uuid4()
        document_id = uuid4()
        original = b"read only in memory"
        encrypted = self.cipher.encrypt(original)
        with TemporaryDirectory() as upload_dir:
            user_dir = Path(upload_dir) / str(user_id)
            user_dir.mkdir()
            document_path = user_dir / "stored.txt"
            document_path.write_bytes(encrypted)
            cursor = FakeCursor(row=("patient-note.txt", document_path.name, "text/plain", True))

            with patch("intake.get_db_connection", return_value=FakeConnection(cursor)):
                document = get_user_document(user_id, document_id, upload_dir, self.key)

            self.assertEqual(document["content"], original)
            self.assertEqual(document_path.read_bytes(), encrypted)

    def test_new_upload_is_encrypted_before_it_is_written(self):
        user_id = uuid4()
        original = b"new patient upload"
        cursor = FakeCursor()
        with TemporaryDirectory() as upload_dir:
            with (
                patch("intake.scan_with_clamav", return_value=True),
                patch("intake.get_db_connection", return_value=FakeConnection(cursor)),
            ):
                result = store_documents(
                    [("note.txt", original)],
                    user_id,
                    upload_dir,
                    "clamav",
                    3310,
                    True,
                    self.key,
                )

            stored_name = f"{result['uploaded'][0]['id']}.txt"
            stored_path = Path(upload_dir) / str(user_id) / stored_name
            encrypted = stored_path.read_bytes()
            self.assertNotEqual(encrypted, original)
            self.assertEqual(self.cipher.decrypt(encrypted), original)
            self.assertEqual(stat.S_IMODE(stored_path.stat().st_mode), 0o600)


if __name__ == "__main__":
    unittest.main()