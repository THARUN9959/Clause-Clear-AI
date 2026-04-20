"""Configuration settings for ClauseClear AI application."""

import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    """Application configuration loaded from environment variables."""

    # API Keys
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

    # Flask
    SECRET_KEY = os.getenv("FLASK_SECRET_KEY", "clauseclear-default-secret")

    # Gemini Model
    GEMINI_MODEL = "gemini-2.5-flash-lite"

    # File Upload
    UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "uploads")
    ALLOWED_EXTENSIONS = {"pdf", "txt"}
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16 MB max upload

    # Session Memory
    MAX_MEMORY_TURNS = 10  # Keep last 10 conversation turns

    @staticmethod
    def init_app():
        """Ensure required directories exist."""
        os.makedirs(Config.UPLOAD_FOLDER, exist_ok=True)
