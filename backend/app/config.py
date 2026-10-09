"""Application configuration loaded from environment variables (.env supported).

No secrets are hard-coded: JWT_SECRET falls back to a random per-process value
(tokens then become invalid on restart) and a warning is logged.
"""
from __future__ import annotations

import logging
import secrets
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent
REPO_DIR = BACKEND_DIR.parent

log = logging.getLogger("resq.config")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(str(REPO_DIR / ".env"), str(BACKEND_DIR / ".env")),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "RESQ-AI"
    version: str = "1.0.0"
    # PostgreSQL in Docker; SQLite fallback for quick local runs and tests.
    database_url: str = f"sqlite:///{(BACKEND_DIR / 'resq.db').as_posix()}"
    redis_url: str = ""
    jwt_secret: str = ""
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 12 * 60

    map_api_key: str = ""
    weather_api_key: str = ""
    traffic_api_key: str = ""
    hospital_api_url: str = ""

    ml_artifacts_dir: str = str(REPO_DIR / "ml" / "artifacts")
    ml_datasets_dir: str = str(REPO_DIR / "ml" / "datasets")
    cors_origins: str = "http://localhost:5173,http://localhost:3000,http://localhost:8080"
    seed_demo_data: bool = True
    iot_enabled: bool = True

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")

    @property
    def data_mode(self) -> str:
        """LIVE only if a real-time traffic provider is configured; otherwise SIMULATION."""
        return "LIVE" if self.traffic_api_key else "SIMULATION"


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    if not s.jwt_secret:
        log.warning("JWT_SECRET not set - using an ephemeral random secret (set it in .env)")
        s.jwt_secret = secrets.token_urlsafe(48)
    Path(s.ml_artifacts_dir).mkdir(parents=True, exist_ok=True)
    Path(s.ml_datasets_dir).mkdir(parents=True, exist_ok=True)
    return s
