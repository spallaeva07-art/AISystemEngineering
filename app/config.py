import os
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Optional

# Load .env from project root (parent of app/), so keys are found even when
# started via Flask reloader or from a different working directory.
_env_path = Path(__file__).resolve().parent.parent / ".env"
if _env_path.exists():
    from dotenv import load_dotenv
    load_dotenv(dotenv_path=_env_path)


@dataclass(frozen=True)
class AppConfig:
    # Security
    SECRET_KEY: str = os.getenv("SECRET_KEY", "dev-secret-change-me")

    # Database
    SQLALCHEMY_DATABASE_URI: str = os.getenv(
        "DATABASE_URL", f"sqlite:///{os.path.abspath('app.db')}"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS: bool = False

    # File uploads
    UPLOAD_FOLDER: str = os.getenv("UPLOAD_FOLDER", os.path.abspath("uploads"))
    MAX_CONTENT_LENGTH: int = int(os.getenv("MAX_CONTENT_LENGTH", str(16 * 1024 * 1024)))  # 16 MB

    # Groq API
    GROQ_API_KEY: Optional[str] = os.getenv("GROQ_API_KEY")
    GROQ_MODEL: str = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
    GROQ_VISION_MODEL: str = os.getenv(
        "GROQ_VISION_MODEL", "meta-llama/llama-4-scout-17b-16e-instruct"
    )
    GROQ_BASE_URL: str = os.getenv("GROQ_BASE_URL", "https://api.groq.com/openai/v1")
    GROQ_TIMEOUT_SECONDS: int = int(os.getenv("GROQ_TIMEOUT_SECONDS", "35"))

    # Recipe image provider (pollinations = AI-generated from dish title)
    RECIPE_IMAGE_PROVIDER: str = os.getenv("RECIPE_IMAGE_PROVIDER", "pollinations")

    def to_dict(self) -> dict:
        """Return a plain dict so Flask's app.config.from_mapping() works correctly.
        Flask's app.config is a dict subclass — it does NOT call .get() on dataclasses,
        so AppConfig must be converted before passing to app.config.update()."""
        return {k: v for k, v in asdict(self).items() if v is not None or k == "GROQ_API_KEY"}