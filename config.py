"""Configuration settings for ClauseClear AI application."""

import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    """Application configuration loaded from environment variables."""

    # ── API Keys ─────────────────────────────────────────────────────────────
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

    # ── Flask ─────────────────────────────────────────────────────────────────
    SECRET_KEY = os.getenv("FLASK_SECRET_KEY")
    if not SECRET_KEY:
        raise RuntimeError(
            "FLASK_SECRET_KEY environment variable is required. "
            "Generate one with: python -c \"import secrets; print(secrets.token_hex(32))\""
        )

    # ── Gemini Model ──────────────────────────────────────────────────────────
    GEMINI_MODEL = "gemini-2.5-flash-lite"

    # ── File Upload ───────────────────────────────────────────────────────────
    UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "uploads")
    ALLOWED_EXTENSIONS = {"pdf", "docx", "png", "jpg", "jpeg"}
    MAX_CONTENT_LENGTH = 10 * 1024 * 1024   # 10 MB — enforced by Flask

    # Accepted MIME types for server-side validation
    ALLOWED_MIME_TYPES = {
        "application/pdf",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "image/png",
        "image/jpeg",
    }

    # ── Session Memory ────────────────────────────────────────────────────────
    MAX_MEMORY_TURNS = 10

    # ── Rate Limiting ─────────────────────────────────────────────────────────
    RATELIMIT_STORAGE_URI = "memory://"

    @staticmethod
    def init_app():
        """Ensure required directories exist."""
        os.makedirs(Config.UPLOAD_FOLDER, exist_ok=True)
        os.makedirs(os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs"), exist_ok=True)
