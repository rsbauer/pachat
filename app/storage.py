from __future__ import annotations

from uuid import UUID, uuid4

from database import get_db_connection


class SessionNotFoundError(Exception):
    pass


class DocumentNotFoundError(Exception):
    pass


def prepare_chat(
    user_id: UUID,
    session_id: UUID | None,
    user_message: str,
    model_name: str,
    document_ids: list[UUID] | None = None,
) -> tuple[UUID, list[dict[str, str]]]:
    document_ids = list(dict.fromkeys(document_ids or []))

    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            if session_id is None:
                session_id = uuid4()
                cursor.execute(
                    """
                    INSERT INTO chat_sessions (id, user_id, title, model_name)
                    VALUES (%s, %s, %s, %s)
                    """,
                    (session_id, user_id, user_message[:80], model_name),
                )
                messages: list[dict[str, str]] = []
            else:
                cursor.execute(
                    "SELECT status FROM chat_sessions WHERE id = %s AND user_id = %s",
                    (session_id, user_id),
                )
                session = cursor.fetchone()
                if session is None or session[0] != "active":
                    raise SessionNotFoundError(str(session_id))

                cursor.execute(
                    """
                    SELECT role, content
                    FROM chat_messages
                    WHERE session_id = %s
                    ORDER BY id
                    """,
                    (session_id,),
                )
                messages = [
                    {"role": role, "content": content}
                    for role, content in cursor.fetchall()
                ]

            for document_id in document_ids:
                cursor.execute(
                    "SELECT id FROM uploaded_documents WHERE id = %s AND user_id = %s",
                    (document_id, user_id),
                )
                if cursor.fetchone() is None:
                    raise DocumentNotFoundError(str(document_id))

            cursor.execute("DELETE FROM chat_session_documents WHERE session_id = %s", (session_id,))
            for document_id in document_ids:
                cursor.execute(
                    "INSERT INTO chat_session_documents (session_id, document_id) VALUES (%s, %s)",
                    (session_id, document_id),
                )

            cursor.execute(
                """
                INSERT INTO chat_messages (session_id, role, content, model_name)
                VALUES (%s, 'user', %s, %s)
                """,
                (session_id, user_message, model_name),
            )
            cursor.execute(
                "UPDATE chat_sessions SET updated_at = NOW() WHERE id = %s",
                (session_id,),
            )

    messages.append({"role": "user", "content": user_message})
    return session_id, messages


def save_assistant_message(user_id: UUID, session_id: UUID, content: str, model_name: str) -> None:
    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO chat_messages (session_id, role, content, model_name)
                SELECT id, 'assistant', %s, %s FROM chat_sessions
                WHERE id = %s AND user_id = %s
                """,
                (content, model_name, session_id, user_id),
            )
            if cursor.rowcount:
                cursor.execute(
                    "UPDATE chat_sessions SET updated_at = NOW() WHERE id = %s AND user_id = %s",
                    (session_id, user_id),
                )


def get_session(user_id: UUID, session_id: UUID) -> dict | None:
    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT title, model_name, created_at, updated_at
                FROM chat_sessions
                WHERE id = %s AND user_id = %s AND status = 'active'
                """,
                (session_id, user_id),
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
                {"role": role, "content": content, "created_at": created_at}
                for role, content, created_at in cursor.fetchall()
            ]
            cursor.execute(
                """
                SELECT documents.id, documents.original_name
                FROM chat_session_documents AS attachments
                JOIN uploaded_documents AS documents ON documents.id = attachments.document_id
                WHERE attachments.session_id = %s AND documents.user_id = %s
                ORDER BY attachments.created_at, documents.original_name
                """,
                (session_id, user_id),
            )
            documents = [
                {"id": str(document_id), "filename": filename}
                for document_id, filename in cursor.fetchall()
            ]

    return {
        "id": session_id,
        "title": session[0],
        "model_name": session[1],
        "created_at": session[2],
        "updated_at": session[3],
        "messages": messages,
        "documents": documents,
    }