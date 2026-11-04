from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import psycopg
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from fastapi import Depends, HTTPException, Request, Response
from starlette.concurrency import run_in_threadpool

from config import settings
from database import get_db_connection

SESSION_COOKIE = "pachat_session"
SESSION_LIFETIME = timedelta(hours=12)
LOGIN_FAILURE_LIMIT = 5
LOGIN_WINDOW = timedelta(minutes=15)
PASSWORD_HASHER = PasswordHasher()
DUMMY_PASSWORD_HASH = PASSWORD_HASHER.hash(secrets.token_urlsafe(24))


class UsernameTakenError(Exception):
    pass


def password_hash(password: str) -> str:
    return PASSWORD_HASHER.hash(password)


def _password_matches(password: str, stored_hash: str) -> bool:
    try:
        return PASSWORD_HASHER.verify(stored_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def create_account(username: str, password: str) -> dict:
    user_id = uuid4()
    stored_hash = password_hash(password)
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO app_users (id, username, display_name, password_hash)
                    VALUES (%s, %s, %s, %s)
                    RETURNING id, username, display_name, role
                    """,
                    (user_id, username, username, stored_hash),
                )
                user = cursor.fetchone()
    except psycopg.errors.UniqueViolation as exc:
        raise UsernameTakenError from exc

    return {"id": user[0], "username": user[1], "display_name": user[2], "role": user[3]}


def authenticate_user(username: str, password: str) -> dict | None:
    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT id, username, display_name, role, password_hash
                FROM app_users
                WHERE LOWER(username) = LOWER(%s) AND password_hash IS NOT NULL
                """,
                (username,),
            )
            user = cursor.fetchone()

    stored_hash = user[4] if user else DUMMY_PASSWORD_HASH
    if not _password_matches(password, stored_hash) or user is None:
        return None
    return {"id": user[0], "username": user[1], "display_name": user[2], "role": user[3]}


def _login_bucket_hash(username: str, client_host: str) -> str:
    message = f"{username.casefold()}\0{client_host}".encode("utf-8")
    key = settings.AUTH_RATE_LIMIT_SECRET.encode("utf-8")
    return hmac.new(key, message, hashlib.sha256).hexdigest()


def login_rate_limit_remaining(username: str, client_host: str) -> int | None:
    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT GREATEST(
                    1,
                    CEIL(EXTRACT(EPOCH FROM window_started_at + INTERVAL '15 minutes' - NOW()))
                )::INTEGER
                FROM auth_login_attempts
                WHERE bucket_hash = %s
                    AND failed_attempts >= %s
                    AND window_started_at > NOW() - INTERVAL '15 minutes'
                """,
                (_login_bucket_hash(username, client_host), LOGIN_FAILURE_LIMIT),
            )
            row = cursor.fetchone()
    return row[0] if row else None


def record_failed_login(username: str, client_host: str) -> None:
    bucket_hash = _login_bucket_hash(username, client_host)
    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO auth_login_attempts (bucket_hash, failed_attempts, window_started_at)
                VALUES (%s, 1, NOW())
                ON CONFLICT (bucket_hash) DO UPDATE SET
                    failed_attempts = CASE
                        WHEN auth_login_attempts.window_started_at <= NOW() - INTERVAL '15 minutes' THEN 1
                        ELSE auth_login_attempts.failed_attempts + 1
                    END,
                    window_started_at = CASE
                        WHEN auth_login_attempts.window_started_at <= NOW() - INTERVAL '15 minutes' THEN NOW()
                        ELSE auth_login_attempts.window_started_at
                    END
                """,
                (bucket_hash,),
            )
            cursor.execute(
                "DELETE FROM auth_login_attempts WHERE window_started_at <= NOW() - INTERVAL '1 day'"
            )


def clear_login_attempts(username: str, client_host: str) -> None:
    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                "DELETE FROM auth_login_attempts WHERE bucket_hash = %s",
                (_login_bucket_hash(username, client_host),),
            )


def _token_digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_session(user_id: UUID) -> str:
    token = secrets.token_urlsafe(32)
    expires_at = datetime.now(timezone.utc) + SESSION_LIFETIME
    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("DELETE FROM auth_sessions WHERE expires_at <= NOW()")
            cursor.execute(
                "INSERT INTO auth_sessions (token_hash, user_id, expires_at) VALUES (%s, %s, %s)",
                (_token_digest(token), user_id, expires_at),
            )
    return token


def get_user_for_session(token: str) -> dict | None:
    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT users.id, users.username, users.display_name, users.role
                FROM auth_sessions AS sessions
                JOIN app_users AS users ON users.id = sessions.user_id
                WHERE sessions.token_hash = %s AND sessions.expires_at > NOW()
                """,
                (_token_digest(token),),
            )
            user = cursor.fetchone()
    if user is None:
        return None
    return {"id": user[0], "username": user[1], "display_name": user[2], "role": user[3]}


def revoke_session(token: str) -> None:
    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("DELETE FROM auth_sessions WHERE token_hash = %s", (_token_digest(token),))


def update_display_name(user_id: UUID, display_name: str) -> dict:
    clean_name = display_name.strip()
    if not clean_name:
        raise HTTPException(status_code=422, detail="Display name cannot be empty")
    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                UPDATE app_users SET display_name = %s
                WHERE id = %s AND password_hash IS NOT NULL
                RETURNING id, username, display_name, role
                """,
                (clean_name, user_id),
            )
            user = cursor.fetchone()
    if user is None:
        raise HTTPException(status_code=404, detail="Account not found")
    return {"id": user[0], "username": user[1], "display_name": user[2], "role": user[3]}


def change_password(user_id: UUID, current_password: str, new_password: str) -> str:
    new_token = secrets.token_urlsafe(32)
    expires_at = datetime.now(timezone.utc) + SESSION_LIFETIME
    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT password_hash FROM app_users WHERE id = %s", (user_id,))
            user = cursor.fetchone()
            if user is None or not _password_matches(current_password, user[0]):
                raise HTTPException(status_code=400, detail="Current password is incorrect")
            cursor.execute(
                "UPDATE app_users SET password_hash = %s WHERE id = %s",
                (password_hash(new_password), user_id),
            )
            cursor.execute("DELETE FROM auth_sessions WHERE user_id = %s", (user_id,))
            cursor.execute(
                "INSERT INTO auth_sessions (token_hash, user_id, expires_at) VALUES (%s, %s, %s)",
                (_token_digest(new_token), user_id, expires_at),
            )
    return new_token


async def get_current_user(request: Request) -> dict:
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        raise HTTPException(status_code=401, detail="Please sign in")
    user = await run_in_threadpool(get_user_for_session, token)
    if user is None:
        raise HTTPException(status_code=401, detail="Please sign in")
    return user


def set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=int(SESSION_LIFETIME.total_seconds()),
        httponly=True,
        secure=settings.APP_ENV.lower() in {"production", "prod"},
        samesite="lax",
        path="/",
    )