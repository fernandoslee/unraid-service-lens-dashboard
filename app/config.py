from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Use /app/data in Docker, otherwise local ./data
_DOCKER_DATA = Path("/app/data")
_LOCAL_DATA = Path(__file__).resolve().parent.parent / "data"
_DATA_DIR = _DOCKER_DATA if _DOCKER_DATA.is_dir() else _LOCAL_DATA

_ENV_FILE = _DATA_DIR / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(_ENV_FILE),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Local Network Services Indexer"
    unraid_host: str = ""
    unraid_api_key: str = ""
    unraid_verify_ssl: bool = False
    poll_interval_seconds: int = 30
    cache_ttl_seconds: int = 10
    data_dir: Path = _DATA_DIR

    @property
    def is_configured(self) -> bool:
        return bool(self.unraid_host and self.unraid_api_key)


@lru_cache
def get_settings() -> Settings:
    return Settings()
