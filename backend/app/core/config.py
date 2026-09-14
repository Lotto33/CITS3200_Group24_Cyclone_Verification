"""Application configuration.

Settings are read from environment variables / a `.env` file (see
`.env.example`) via pydantic-settings.
"""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/app/core/config.py -> repository root
PROJECT_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    PROJECT_NAME: str = "Cyclone Verification API"
    VERSION: str = "0.1.0"
    API_V1_PREFIX: str = "/api/v1"

    # Comma-separated list of allowed CORS origins, e.g. "http://localhost:8000"
    BACKEND_CORS_ORIGINS: str = ""

    # SQLAlchemy URL. SQLite is the default so the backend runs with no setup;
    # every model is written to work unchanged on PostgreSQL, e.g.
    #   postgresql+psycopg://user:pass@localhost:5432/cyclone
    DATABASE_URL: str = "sqlite+pysqlite:///./cyclone.db"

    # Echo every statement SQLAlchemy emits. Noisy; debugging only.
    SQL_ECHO: bool = False

    # Where the raw/derived cyclone data lives (git-ignored, see README).
    DATA_DIR: Path = PROJECT_ROOT / "data"

    # Upper bound on the number of geometry vertices a single response may
    # carry. See app/api/v1/endpoints/bulletins.py.
    MAX_RESPONSE_VERTICES: int = 200_000

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def cors_origins(self) -> list[str]:
        """BACKEND_CORS_ORIGINS split into a list, blanks dropped."""
        return [o.strip() for o in self.BACKEND_CORS_ORIGINS.split(",") if o.strip()]


settings = Settings()
