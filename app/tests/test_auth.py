import unittest
from unittest.mock import patch
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from auth import _password_matches, _recovery_code_hash, create_account, create_session, password_hash, recover_account
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


class RecoveryCodeTests(unittest.TestCase):
    def test_registration_returns_code_but_stores_only_hash(self):
        recovery_code = "1234567890abcdef1234567890abcdef"
        statements = []

        class Cursor:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return None

            def execute(self, query, params=None):
                statements.append((query, params))

            def fetchone(self):
                return uuid4(), "patient.test", "patient.test", "user"

        class Connection:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return None

            def cursor(self):
                return Cursor()

        with (
            patch("auth.get_db_connection", return_value=Connection()),
            patch("auth.password_hash", return_value="password-hash"),
            patch("auth.secrets.token_hex", return_value=recovery_code),
        ):
            account = create_account("patient.test", "a long test password")

        self.assertEqual(account["recovery_code"], recovery_code)
        self.assertEqual(statements[0][1][-1], _recovery_code_hash(recovery_code))
        self.assertNotIn(recovery_code, statements[0][1])

    def test_valid_code_is_consumed_and_all_sessions_are_revoked(self):
        recovery_code = "1234567890abcdef1234567890abcdef"
        user_id = uuid4()
        statements = []

        class Cursor:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return None

            def execute(self, query, params=None):
                statements.append((query, params))

            def fetchone(self):
                return user_id, _recovery_code_hash(recovery_code)

        class Connection:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return None

            def cursor(self):
                return Cursor()

        with (
            patch("auth.get_db_connection", return_value=Connection()),
            patch("auth.password_hash", return_value="new-password-hash"),
        ):
            recovered = recover_account("patient.test", recovery_code, "new long password")

        self.assertTrue(recovered)
        self.assertIn("recovery_code_hash = NULL", statements[1][0])
        self.assertEqual(statements[2][0], "DELETE FROM auth_sessions WHERE user_id = %s")
        self.assertEqual(statements[2][1], (user_id,))

    def test_invalid_code_does_not_change_password(self):
        statements = []

        class Cursor:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return None

            def execute(self, query, params=None):
                statements.append((query, params))

            def fetchone(self):
                return uuid4(), _recovery_code_hash("a" * 32)

        class Connection:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return None

            def cursor(self):
                return Cursor()

        with patch("auth.get_db_connection", return_value=Connection()):
            recovered = recover_account("patient.test", "b" * 32, "new long password")

        self.assertFalse(recovered)
        self.assertEqual(len(statements), 1)


class RouteTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(test_app)

    def test_api_models_requires_login(self):
        response = self.client.get("/api/models")

        self.assertEqual(response.status_code, 401)

    @patch("routes.set_session_cookie")
    @patch("routes.create_session", return_value="opaque-session-token")
    @patch(
        "routes.create_account",
        return_value={
            "id": uuid4(),
            "username": "patient.test",
            "display_name": "Patient",
            "role": "user",
            "recovery_code": "1234567890abcdef1234567890abcdef",
        },
    )
    def test_registration_returns_recovery_code_once(self, _create_account, _create_session, _set_cookie):
        response = self.client.post(
            "/api/auth/register",
            json={"username": "patient.test", "password": "long test password"},
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["recovery_code"], "1234567890abcdef1234567890abcdef")

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

    @patch("routes.clear_login_attempts")
    @patch("routes.recover_account", return_value=True)
    @patch("routes.login_rate_limit_remaining", return_value=None)
    def test_recovery_resets_password_without_returning_code(self, _limit, recover, clear_attempts):
        response = self.client.post(
            "/api/auth/recover",
            json={
                "username": "patient.test",
                "recovery_code": "1234567890abcdef1234567890abcdef",
                "new_password": "a new long password",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})
        recover.assert_called_once_with("patient.test", "1234567890abcdef1234567890abcdef", "a new long password")
        clear_attempts.assert_called_once_with("recovery:patient.test", "testclient")

    @patch("routes.record_failed_login")
    @patch("routes.recover_account", return_value=False)
    @patch("routes.login_rate_limit_remaining", return_value=None)
    def test_invalid_recovery_details_are_generic_and_counted(self, _limit, _recover, record_failure):
        response = self.client.post(
            "/api/auth/recover",
            json={
                "username": "patient.test",
                "recovery_code": "1234567890abcdef1234567890abcdef",
                "new_password": "a new long password",
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "Unable to recover this account with those details")
        record_failure.assert_called_once_with("recovery:patient.test", "testclient")


if __name__ == "__main__":
    unittest.main()