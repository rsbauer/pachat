import os


def get_setting(name: str, default: str) -> str:
    value = os.getenv(name)
    if value is None or value == "":
        return default
    return value


class Settings:
    APP_ENV = get_setting("APP_ENV", "development")
    APP_PORT = int(get_setting("APP_PORT", "9105"))
    DATABASE_URL = get_setting("DATABASE_URL", "postgresql://pachat:secret@db:5432/pachat")
    OLLAMA_BASE_URL = get_setting("OLLAMA_BASE_URL", "http://localhost:11434")
    OLLAMA_MODEL = get_setting(
        "OLLAMA_MODEL",
        "hf.co/DevQuasar/google.medgemma-4b-it-GGUF:Q4_K_M",
    )


settings = Settings()
