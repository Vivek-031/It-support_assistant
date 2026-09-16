import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

# Real environment variables take precedence over values in .env.
load_dotenv(BASE_DIR / ".env")


def _env(name: str, default: str) -> str:
    return (os.getenv(name) or default).strip()


class Settings:
    def __init__(self) -> None:
        self.llm_provider = _env("LLM_PROVIDER", "groq").lower()
        self.groq_api_key = _env("GROQ_API_KEY", "")
        self.groq_model = _env("GROQ_MODEL", "llama-3.3-70b-versatile")
        self.gemini_api_key = _env("GEMINI_API_KEY", "")
        self.gemini_model = _env("GEMINI_MODEL", "gemini-2.5-flash")
        self.llm_timeout = float(_env("LLM_TIMEOUT_SECONDS", "30"))
        self.kb_top_k = int(_env("KB_TOP_K", "3"))
        self.database_url = _env("DATABASE_URL", f"sqlite:///{BASE_DIR / 'support.db'}")

    @property
    def llm_api_key(self) -> str:
        if self.llm_provider == "groq":
            return self.groq_api_key
        if self.llm_provider == "gemini":
            return self.gemini_api_key
        return ""


settings = Settings()
