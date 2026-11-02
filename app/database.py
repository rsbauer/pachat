import os
from uuid import UUID

import psycopg


def get_db_connection():
    return psycopg.connect(os.getenv("DATABASE_URL", "postgresql://pachat:secret@db:5432/pachat"))


def init_db() -> None:
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS chat_sessions (
                    id UUID PRIMARY KEY,
                    title TEXT,
                    model_name TEXT NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    status TEXT NOT NULL DEFAULT 'active'
                );
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS chat_messages (
                    id BIGSERIAL PRIMARY KEY,
                    session_id UUID NOT NULL REFERENCES chat_sessions(id) ON DELETE CASCADE,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    model_name TEXT,
                    token_count INTEGER
                );
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS app_users (
                    id UUID PRIMARY KEY,
                    display_name TEXT NOT NULL,
                    is_placeholder BOOLEAN NOT NULL DEFAULT FALSE,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS uploaded_documents (
                    id UUID PRIMARY KEY,
                    user_id UUID NOT NULL REFERENCES app_users(id),
                    original_name TEXT NOT NULL,
                    stored_name TEXT NOT NULL,
                    mime_type TEXT NOT NULL,
                    size_bytes BIGINT NOT NULL,
                    is_encrypted BOOLEAN NOT NULL DEFAULT FALSE,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );
                """
            )
            cur.execute(
                """
                INSERT INTO app_users (id, display_name, is_placeholder)
                VALUES (%s, 'Local test user', TRUE)
                ON CONFLICT (id) DO NOTHING;
                """,
                (UUID("00000000-0000-0000-0000-000000000001"),),
            )
            conn.commit()
