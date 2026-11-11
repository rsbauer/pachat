import unittest
from datetime import datetime, timezone
from unittest.mock import patch
from uuid import uuid4

from storage import DocumentNotFoundError, get_session, prepare_chat


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


class SessionDocumentTests(unittest.TestCase):
    def test_prepare_chat_links_only_documents_owned_by_user(self):
        user_id = uuid4()
        document_id = uuid4()
        cursor = FakeCursor(fetchone_values=[(document_id,)])

        with patch("storage.get_db_connection", return_value=FakeConnection(cursor)):
            session_id, messages = prepare_chat(
                user_id,
                None,
                "Review this file",
                "model",
                [document_id],
            )

        self.assertEqual(messages, [{"role": "user", "content": "Review this file"}])
        ownership_check = next(query for query, _params in cursor.statements if "FROM uploaded_documents" in query)
        self.assertIn("user_id = %s", ownership_check)
        attachment = next(
            (query, params)
            for query, params in cursor.statements
            if query.startswith("INSERT INTO chat_session_documents")
        )
        self.assertEqual(attachment[1], (session_id, document_id))

    def test_prepare_chat_rejects_another_users_document(self):
        cursor = FakeCursor(fetchone_values=[None])
        with patch("storage.get_db_connection", return_value=FakeConnection(cursor)):
            with self.assertRaises(DocumentNotFoundError):
                prepare_chat(uuid4(), None, "Review this file", "model", [uuid4()])

        self.assertFalse(any(query.startswith("INSERT INTO chat_session_documents") for query, _params in cursor.statements))

    def test_session_restore_returns_attached_file_references(self):
        user_id = uuid4()
        session_id = uuid4()
        document_id = uuid4()
        timestamp = datetime.now(timezone.utc)
        cursor = FakeCursor(
            fetchone_values=[("Review", "model", timestamp, timestamp)],
            fetchall_values=[[("user", "Review this file", timestamp)], [(document_id, "note.txt")]],
        )

        with patch("storage.get_db_connection", return_value=FakeConnection(cursor)):
            session = get_session(user_id, session_id)

        self.assertEqual(session["documents"], [{"id": str(document_id), "filename": "note.txt"}])
        self.assertEqual(session["messages"][0]["content"], "Review this file")

    def test_prepare_chat_links_more_than_five_documents(self):
        user_id = uuid4()
        document_ids = [uuid4() for _ in range(6)]
        cursor = FakeCursor(fetchone_values=[(document_id,) for document_id in document_ids])

        with patch("storage.get_db_connection", return_value=FakeConnection(cursor)):
            prepare_chat(user_id, None, "Review these files", "model", document_ids)

        attachments = [
            params
            for query, params in cursor.statements
            if query.startswith("INSERT INTO chat_session_documents")
        ]
        self.assertEqual(len(attachments), 6)
        self.assertEqual([attachment[1] for attachment in attachments], document_ids)


if __name__ == "__main__":
    unittest.main()