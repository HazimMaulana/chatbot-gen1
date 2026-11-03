"""Pengaturan proyek. Environment variable dapat menimpa nilai default."""

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent / ".env")


class Config:
    DATABASE_URL = os.getenv("DATABASE_URL", "")
    DB_HOST = os.getenv("POSTGRES_HOST", "127.0.0.1")
    DB_PORT = os.getenv("POSTGRES_PORT", "5433")
    DB_NAME = os.getenv("POSTGRES_DB", "warehouse")
    DB_USER = os.getenv("POSTGRES_USER", "warehouse")
    DB_PASSWORD = os.getenv("POSTGRES_PASSWORD", "")
    MODEL = os.getenv("OLLAMA_MODEL", "qwen3:1.7b")
    OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
    SYSTEM_PROMPT = (
        "Kamu adalah asisten belajar yang ramah. "
        "Jawab dalam bahasa Indonesia dengan singkat dan jelas. "
        "Jika tidak tahu, katakan bahwa kamu tidak tahu."
    )
    MAX_MESSAGE_CHARS = 4000
    MAX_CONTENT_LENGTH = 64 * 1024
