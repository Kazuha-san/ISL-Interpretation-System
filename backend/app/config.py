"""
app/config.py

Loads environment variables from .env and exposes them as a single
Settings object. Import `settings` anywhere in the backend instead of
calling os.getenv directly, so there is one source of truth and startup
fails fast if a required key is missing.
"""

import os
from dotenv import load_dotenv

load_dotenv()


def _require(key: str) -> str:
    value = os.getenv(key)
    if not value:
        raise RuntimeError(
            f"Missing required environment variable: {key}. "
            f"Check your .env file against .env.example."
        )
    return value


class Settings:
    # Required — app cannot function without these
    GROQ_API_KEY: str = _require("GROQ_API_KEY")
    SUPABASE_URL: str = _require("SUPABASE_URL")
    SUPABASE_KEY: str = _require("SUPABASE_KEY")

    # Optional — safe defaults for local/dev use
    WHISPER_MODEL: str = os.getenv("WHISPER_MODEL", "base")
    KIOSK_ID: str = os.getenv("KIOSK_ID", "kiosk_dev_01")
    KIOSK_LOCATION: str = os.getenv("KIOSK_LOCATION", "Development")

    # Local SQLite path — not in .env, fixed by repo convention
    LOCAL_DB_PATH: str = os.getenv("LOCAL_DB_PATH", "data/isl.db")


settings = Settings()
