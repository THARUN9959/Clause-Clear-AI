"""Configuration settings for ClauseClear AI application."""

import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    """Application configuration loaded from environment variables."""

    # ── API Keys ─────────────────────────────────────────────────────────────
    GEMINI_API_KEY    = os.getenv("GEMINI_API_KEY",    "")   # Primary   (1st)
    DEEPSEEK_API_KEY  = os.getenv("DEEPSEEK_API_KEY",  "")   # Fallback  (2nd)
    OPENAI_API_KEY    = os.getenv("OPENAI_API_KEY",    "")   # Fallback  (3rd)
    ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")   # Fallback  (4th)

    # ── Flask ─────────────────────────────────────────────────────────────────
    SECRET_KEY = os.getenv("FLASK_SECRET_KEY")
    if not SECRET_KEY:
        raise RuntimeError(
            "FLASK_SECRET_KEY environment variable is required. "
            "Generate one with: python -c \"import secrets; print(secrets.token_hex(32))\""
        )

    # ── AI Models ────────────────────────────────────────────────────────────
    # Override any of these via the corresponding env var in .env
    GEMINI_MODEL    = os.getenv("GEMINI_MODEL",    "gemini-2.5-flash")
    DEEPSEEK_MODEL  = os.getenv("DEEPSEEK_MODEL",  "deepseek-chat")   # deepseek-reasoner for R1
    OPENAI_MODEL    = os.getenv("OPENAI_MODEL",    "gpt-4o-mini")
    CLAUDE_MODEL    = os.getenv("CLAUDE_MODEL",    "claude-3-5-haiku-latest")

    # ── Analysis limits ───────────────────────────────────────────────────────
    MIN_CONTRACT_LENGTH = 100   # reject contracts shorter than this (likely noise)

    # ── File Upload ───────────────────────────────────────────────────────────
    UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "uploads")
    ALLOWED_EXTENSIONS = {"pdf", "docx", "png", "jpg", "jpeg", "txt"}
    MAX_CONTENT_LENGTH = 10 * 1024 * 1024   # 10 MB — enforced by Flask

    # Accepted MIME types for server-side validation
    ALLOWED_MIME_TYPES = {
        "application/pdf",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "image/png",
        "image/jpeg",
        "text/plain",
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
