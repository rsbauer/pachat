from __future__ import annotations

import shutil
from pathlib import Path
from uuid import UUID

from database import get_db_connection


def list_users() -> list[dict]:
    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT users.id, users.username, users.display_name, users.role, users.created_at,
                    (SELECT COUNT(*) FROM chat_sessions WHERE user_id = users.id),
                    (SELECT COUNT(*) FROM uploaded_documents WHERE user_id = users.id),
                    (SELECT COALESCE(SUM(size_bytes), 0) FROM uploaded_documents WHERE user_id = users.id)
                FROM app_users AS users
                WHERE users.password_hash IS NOT NULL AND users.is_placeholder = FALSE
                ORDER BY users.created_at DESC
                """
            )
            rows = cursor.fetchall()
    return [
        {
            "id": str(row[0]),
            "username": row[1],
            "display_name": row[2],
            "role": row[3],
            "created_at": row[4],
            "chat_count": row[5],
            "file_count": row[6],
            "storage_bytes": row[7],
        }
        for row in rows
    ]


def get_user_detail(user_id: UUID) -> dict | None:
    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT id, username, display_name, role, created_at
                FROM app_users
                WHERE id = %s AND password_hash IS NOT NULL AND is_placeholder = FALSE
                """,
                (user_id,),
            )
            user = cursor.fetchone()
            if user is None:
                return None

            cursor.execute(
                """
                SELECT id, title, model_name, created_at, updated_at, status,
                    (SELECT COUNT(*) FROM chat_messages WHERE session_id = chat_sessions.id)
                FROM chat_sessions
                WHERE user_id = %s
                ORDER BY updated_at DESC
                """,
                (user_id,),
            )
            sessions = [
                {
                    "id": str(row[0]),
                    "title": row[1] or "New conversation",
                    "model_name": row[2],
                    "created_at": row[3],
                    "updated_at": row[4],
                    "status": row[5],
                    "message_count": row[6],
                }
                for row in cursor.fetchall()
            ]
            cursor.execute(
                """
                SELECT id, original_name, mime_type, size_bytes, is_encrypted, created_at
                FROM uploaded_documents
                WHERE user_id = %s
                ORDER BY created_at DESC
                """,
                (user_id,),
            )
            documents = [
                {
                    "id": str(row[0]),
                    "filename": row[1],
                    "mime_type": row[2],
                    "size_bytes": row[3],
                    "is_encrypted": row[4],
                    "created_at": row[5],
                }
                for row in cursor.fetchall()
            ]

    return {
        "user": {
            "id": str(user[0]),
            "username": user[1],
            "display_name": user[2],
            "role": user[3],
            "created_at": user[4],
        },
        "sessions": sessions,
        "documents": documents,
        "storage_bytes": sum(document["size_bytes"] for document in documents),
    }


def get_chat_session(session_id: UUID) -> dict | None:
    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT title, model_name, created_at, updated_at, status
                FROM chat_sessions
                WHERE id = %s
                """,
                (session_id,),
            )
            session = cursor.fetchone()
            if session is None:
                return None
            cursor.execute(
                """
                SELECT role, content, created_at
                FROM chat_messages
                WHERE session_id = %s
                ORDER BY id
                """,
                (session_id,),
            )
            messages = [
                {"role": row[0], "content": row[1], "created_at": row[2]}
                for row in cursor.fetchall()
            ]
    return {
        "id": str(session_id),
        "title": session[0] or "New conversation",
        "model_name": session[1],
        "created_at": session[2],
        "updated_at": session[3],
        "status": session[4],
        "messages": messages,
    }


def delete_chat_session(session_id: UUID) -> bool:
    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("DELETE FROM chat_sessions WHERE id = %s RETURNING id", (session_id,))
            return cursor.fetchone() is not None


def delete_document(document_id: UUID, upload_dir: str) -> bool:
    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                "DELETE FROM uploaded_documents WHERE id = %s RETURNING user_id, stored_name",
                (document_id,),
            )
            row = cursor.fetchone()
    if row is None:
        return False

    user_id, stored_name = row
    if Path(stored_name).name == stored_name:
        (Path(upload_dir) / str(user_id) / stored_name).unlink(missing_ok=True)
    return True


def delete_user(user_id: UUID, upload_dir: str) -> bool:
    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT id FROM app_users
                WHERE id = %s AND password_hash IS NOT NULL AND is_placeholder = FALSE
                """,
                (user_id,),
            )
            if cursor.fetchone() is None:
                return False
            cursor.execute("DELETE FROM uploaded_documents WHERE user_id = %s", (user_id,))
            cursor.execute(
                """
                DELETE FROM app_users
                WHERE id = %s AND password_hash IS NOT NULL AND is_placeholder = FALSE
                RETURNING id
                """,
                (user_id,),
            )
            deleted = cursor.fetchone()
    if deleted is None:
        return False

    user_directory = Path(upload_dir) / str(user_id)
    if user_directory.exists():
        shutil.rmtree(user_directory)
    return True