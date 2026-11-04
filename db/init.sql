CREATE TABLE IF NOT EXISTS app_users (
    id UUID PRIMARY KEY,
    username TEXT,
    display_name TEXT NOT NULL,
    password_hash TEXT,
    recovery_code_hash TEXT,
    role TEXT NOT NULL DEFAULT 'user',
    is_placeholder BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS app_users_username_unique_idx
ON app_users (LOWER(username)) WHERE username IS NOT NULL;

CREATE TABLE IF NOT EXISTS auth_sessions (
    token_hash CHAR(64) PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES app_users(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX IF NOT EXISTS auth_sessions_expiry_idx ON auth_sessions (expires_at);

CREATE TABLE IF NOT EXISTS auth_login_attempts (
    bucket_hash CHAR(64) PRIMARY KEY,
    failed_attempts INTEGER NOT NULL,
    window_started_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX IF NOT EXISTS auth_login_attempts_window_idx ON auth_login_attempts (window_started_at);

CREATE TABLE IF NOT EXISTS chat_sessions (
    id UUID PRIMARY KEY,
    user_id UUID REFERENCES app_users(id) ON DELETE CASCADE,
    title TEXT,
    model_name TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    status TEXT NOT NULL DEFAULT 'active'
);

CREATE TABLE IF NOT EXISTS chat_messages (
    id BIGSERIAL PRIMARY KEY,
    session_id UUID NOT NULL REFERENCES chat_sessions(id) ON DELETE CASCADE,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    model_name TEXT,
    token_count INTEGER
);

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

CREATE TABLE IF NOT EXISTS chat_session_documents (
    session_id UUID NOT NULL REFERENCES chat_sessions(id) ON DELETE CASCADE,
    document_id UUID NOT NULL REFERENCES uploaded_documents(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (session_id, document_id)
);

CREATE TABLE IF NOT EXISTS app_settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
