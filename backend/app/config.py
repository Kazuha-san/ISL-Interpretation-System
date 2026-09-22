"""
app/config.py

Loads environment variables from .env and exposes them as a single
Settings object. Import `settings` anywhere in the backend instead of
calling os.getenv directly, so there is one source of truth.

Nothing in this app is required to be online. GROQ_API_KEY is optional:
when it is missing, the Groq fallback step is skipped everywhere and the
local rule-based engine (app/services/local_gloss.py) is used on its own.
"""

import os
from dotenv import load_dotenv
from pathlib import Path

load_dotenv()


class Settings:
    # Optional — enables the online Groq fallback in gloss.py / convert_to_gloss_smart.
    # Leave blank to run fully offline on the local rule engine.
    GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")

    KIOSK_ID: str = os.getenv("KIOSK_ID", "kiosk_dev_01")
    KIOSK_LOCATION: str = os.getenv("KIOSK_LOCATION", "Development")
    CORS_ALLOWED_ORIGINS: list[str] = os.getenv(
        "CORS_ALLOWED_ORIGINS", "http://localhost:5173"
    ).split(",")

    # Local SQLite path — the only datastore this app uses.
    LOCAL_DB_PATH: str = os.getenv("LOCAL_DB_PATH", "data/isl.db")

    # Keypoint mock mode — when True, returns synthetic placeholder sequences.
    # Set to "false" once real keypoint JSON files are seeded into sign_clips.
    MOCK_KEYPOINTS: bool = os.getenv("MOCK_KEYPOINTS", "true").lower() == "true"

    # Pipeline B: path to the trained sign-recognition model weights.
    # No model ships with this repo yet — recognition.py checks this path
    # at startup and runs in a clearly-labelled stub mode until it's set.
    RECOGNIZER_MODEL_PATH: str = os.getenv("RECOGNIZER_MODEL_PATH", "")

    @property
    def groq_enabled(self) -> bool:
        return bool(self.GROQ_API_KEY)

    @property
    def recognizer_enabled(self) -> bool:
        return bool(self.RECOGNIZER_MODEL_PATH) and Path(self.RECOGNIZER_MODEL_PATH).exists()


settings = Settings()
