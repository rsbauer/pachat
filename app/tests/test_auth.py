import unittest
from unittest.mock import patch
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from auth import _password_matches, create_session, password_hash
from models import PasswordUpdate, RegisterRequest
from routes import router
from storage import get_session

test_app = FastAPI()
test_app.include_router(router)


class PasswordTests(unittest.TestCase):
    def test_password_is_stored_as_argon2id_hash(self):
        password = "a long test password"
        hashed = password_hash(password)

        self.assertTrue(hashed.startswith("$argon2id$"))
        self.assertNotEqual(hashed, password)
        self.assertTrue(_password_matches(password, hashed))
        self.assertFalse(_password_matches("incorrect password", hashed))

    def test_registration_requires_a_long_password(self):
        with self.assertRaises(ValidationError):
            RegisterRequest(username="patient.test", password="123456789")

        self.assertEqual(RegisterRequest(username="patient.test", password="1234567890").password, "1234567890")

    def test_password_change_requires_at_least_ten_characters(self):
        with self.assertRaises(ValidationError):
            PasswordUpdate(current_password="current", new_password="123456789")

        update = PasswordUpdate(current_password="current", new_password="1234567890")
        self.assertEqual(update.new_password, "1234567890")


class SessionTests(unittest.TestCase):
    def test_raw_session_token_is_not_stored(self):
        statements = []

        class Cursor:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return None

            def execute(self, query, params=None):
                statements.append((query, params))

        class Connection:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return None

            def cursor(self):
                return Cursor()

        with patch("auth.get_db_connection", return_value=Connection()):
            token = create_session(uuid4())

        insert_params = statements[-1][1]
        self.assertNotEqual(insert_params[0], token)
        self.assertEqual(len(insert_params[0]), 64)

    def test_session_lookup_is_scoped_to_user_id(self):
        statements = []

        class Cursor:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return None

            def execute(self, query, params=None):
                statements.append((query, params))

            def fetchone(self):
                return None

        class Connection:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return None

            def cursor(self):
                return Cursor()

        user_id = uuid4()
        session_id = uuid4()
        with patch("storage.get_db_connection", return_value=Connection()):
            session = get_session(user_id, session_id)

        self.assertIsNone(session)
        self.assertIn("user_id = %s", statements[0][0])
        self.assertEqual(statements[0][1], (session_id, user_id))


class RouteTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(test_app)

    def test_api_models_requires_login(self):
        response = self.client.get("/api/models")

        self.assertEqual(response.status_code, 401)

    def test_chat_and_file_endpoints_require_login(self):
        chat_response = self.client.post("/api/chat", json={"message": "test"})
        files_response = self.client.get("/api/files")
        upload_response = self.client.post(
            "/api/uploads",
            files={"files": ("note.txt", b"test content", "text/plain")},
        )

        self.assertEqual(chat_response.status_code, 401)
        self.assertEqual(files_response.status_code, 401)
        self.assertEqual(upload_response.status_code, 401)

    @patch("routes.create_session", return_value="opaque-session-token")
    @patch("routes.clear_login_attempts")
    @patch("routes.login_rate_limit_remaining", return_value=None)
    @patch(
        "routes.authenticate_user",
        return_value={"id": uuid4(), "username": "patient.test", "display_name": "Patient", "role": "user"},
    )
    def test_login_sets_http_only_same_site_cookie(self, _authenticate, _limit, _clear, _create_session):
        response = self.client.post(
            "/api/auth/login",
            json={"username": "patient.test", "password": "test-password"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("httponly", response.headers["set-cookie"].lower())
        self.assertIn("samesite=lax", response.headers["set-cookie"].lower())
        self.assertNotIn("opaque-session-token", response.text)
        _clear.assert_called_once_with("patient.test", "testclient")

    @patch("routes.record_failed_login")
    @patch("routes.authenticate_user", return_value=None)
    @patch("routes.login_rate_limit_remaining", return_value=None)
    def test_failed_login_records_attempt(self, _limit, _authenticate, record_failure):
        response = self.client.post(
            "/api/auth/login",
            json={"username": "patient.test", "password": "wrong-password"},
        )

        self.assertEqual(response.status_code, 401)
        record_failure.assert_called_once_with("patient.test", "testclient")

    @patch("routes.authenticate_user")
    @patch("routes.login_rate_limit_remaining", return_value=47)
    def test_login_rate_limit_blocks_before_password_check(self, _limit, authenticate):
        response = self.client.post(
            "/api/auth/login",
            json={"username": "patient.test", "password": "wrong-password"},
        )

        self.assertEqual(response.status_code, 429)
        self.assertEqual(response.headers["retry-after"], "47")
        authenticate.assert_not_called()


if __name__ == "__main__":
    unittest.main()