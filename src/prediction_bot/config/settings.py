"""Configuration via environment variables and .env file."""

from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Kalshi
    kalshi_api_key: str = ""
    kalshi_base_url: str = "https://external-api.kalshi.com/trade-api/v2"

    # Kalshi RSA authentication
    # Key ID from Kalshi account page (starts with 'KK-').
    kalshi_key_id: str = ""
    # Path to RSA private key PEM file, or the PEM content itself.
    kalshi_private_key_path: str = ""

    # Logging
    log_level: str = "INFO"

    # Data directories
    data_dir: Path = Path("data")
    raw_dir: Path = Path("data/raw")
    processed_dir: Path = Path("data/processed")
    features_dir: Path = Path("data/features")
    models_dir: Path = Path("data/models")
    snapshots_dir: Path = Path("data/snapshots")
    results_dir: Path = Path("data/results")

    # Historical data scope
    historical_max_events: int = 50000

    # HTTP client
    http_timeout: int = 30
    http_max_retries: int = 3
    http_rate_limit_calls_per_second: float = 5.0

    def ensure_directories(self) -> None:
        """Create all configured data directories if they don't exist."""
        for dir_attr in [
            "data_dir", "raw_dir", "processed_dir", "features_dir",
            "models_dir", "snapshots_dir", "results_dir",
        ]:
            path = getattr(self, dir_attr)
            if isinstance(path, Path) and not path.is_absolute():
                path.mkdir(parents=True, exist_ok=True)


_settings: Settings | None = None


def get_settings() -> Settings:
    """Return the cached Settings instance, creating it on first call."""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
