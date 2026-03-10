import os
from dotenv import load_dotenv

load_dotenv()


class Settings:
    """
    Centralized application configuration.
    Every value is loaded from .env for easy production switching.
    """

    # ── Google Gemini AI ──
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
    GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
    GEMINI_MAX_RETRIES: int = int(os.getenv("GEMINI_MAX_RETRIES", "3"))
    GEMINI_RETRY_DELAY: int = int(os.getenv("GEMINI_RETRY_DELAY", "2"))

    # ── PYQ Backend API ──
    PYQ_APPROVED_PAPERS_URL: str = os.getenv("PYQ_APPROVED_PAPERS_URL", "https://api.rohitranjan.in/api/v1/questionPaper/getApprovedQuestionPapers")

    # ── MongoDB ──
    MONGODB_URL: str = os.getenv("MONGODB_URL", "mongodb://localhost:27017")
    MONGODB_DB_NAME: str = os.getenv("MONGODB_DB_NAME", "ai_microservices")

    # ── Server ──
    APP_HOST: str = os.getenv("APP_HOST", "0.0.0.0")
    APP_PORT: int = int(os.getenv("APP_PORT", "8000"))
    API_REQUEST_TIMEOUT: int = int(os.getenv("API_REQUEST_TIMEOUT", "30"))
    APP_VERSION: str = "2.0.0"

    # ── CORS ──
    CORS_ORIGINS: str = os.getenv("CORS_ORIGINS", "*")

    # ── JWT Authentication ──
    JWT_SECRET_KEY: str = os.getenv("JWT_SECRET_KEY", "")
    JWT_ALGORITHM: str = os.getenv("JWT_ALGORITHM", "HS256")

    @property
    def cors_origin_list(self):
        """Parse comma-separated CORS origins into a list."""
        if self.CORS_ORIGINS == "*":
            return ["*"]
        return [o.strip() for o in self.CORS_ORIGINS.split(",")]


settings = Settings()
