import os
import psycopg


def get_db_connection():
    return psycopg.connect(os.getenv("DATABASE_URL", "postgresql://pachat:secret@db:5432/pachat"))


def init_db() -> None:
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS app_users (
                    id UUID PRIMARY KEY,
                    username TEXT,
                    display_name TEXT NOT NULL,
                    password_hash TEXT,
                    role TEXT NOT NULL DEFAULT 'user',
                    is_placeholder BOOLEAN NOT NULL DEFAULT FALSE,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );
                """
            )
            cur.execute("ALTER TABLE app_users ADD COLUMN IF NOT EXISTS username TEXT;")
            cur.execute("ALTER TABLE app_users ADD COLUMN IF NOT EXISTS password_hash TEXT;")
            cur.execute("ALTER TABLE app_users ADD COLUMN IF NOT EXISTS role TEXT NOT NULL DEFAULT 'user';")
            cur.execute(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS app_users_username_unique_idx
                ON app_users (LOWER(username)) WHERE username IS NOT NULL;
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS auth_sessions (
                    token_hash CHAR(64) PRIMARY KEY,
                    user_id UUID NOT NULL REFERENCES app_users(id) ON DELETE CASCADE,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    expires_at TIMESTAMPTZ NOT NULL
                );
                """
            )
            cur.execute("CREATE INDEX IF NOT EXISTS auth_sessions_expiry_idx ON auth_sessions (expires_at);")
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS chat_sessions (
                    id UUID PRIMARY KEY,
                    user_id UUID REFERENCES app_users(id) ON DELETE CASCADE,
                    title TEXT,
                    model_name TEXT NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    status TEXT NOT NULL DEFAULT 'active'
                );
                """
            )
            cur.execute(
                "ALTER TABLE chat_sessions ADD COLUMN IF NOT EXISTS user_id UUID REFERENCES app_users(id) ON DELETE CASCADE;"
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
            conn.commit()
