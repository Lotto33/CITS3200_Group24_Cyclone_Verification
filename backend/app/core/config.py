"""Application configuration.

Settings are read from environment variables / a `.env` file (see
`.env.example`) via pydantic-settings.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    PROJECT_NAME: str = "Cyclone Verification API"
    VERSION: str = "0.1.0"
    API_V1_PREFIX: str = "/api/v1"

    # Comma-separated list of allowed CORS origins, e.g. "http://localhost:8000"
    BACKEND_CORS_ORIGINS: str = ""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    REPO_ROOT = ...
    DATA_DIR = REPO_ROOT / "data"
    UPLOAD_DIR = DATA_DIR / "uploads"
    GEOJSON_DIR = DATA_DIR / "geojson"


settings = Settings()
