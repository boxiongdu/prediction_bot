"""Path resolution utilities."""

from __future__ import annotations

from pathlib import Path

from prediction_bot.config.settings import get_settings


def project_root() -> Path:
    """Return the project root directory (parent of src/prediction_bot)."""
    return Path(__file__).resolve().parent.parent.parent


def resolve_data_path(path: str | Path) -> Path:
    """Resolve a path relative to the data directory."""
    settings = get_settings()
    data_dir = settings.data_dir
    resolved = Path(path)
    if not resolved.is_absolute():
        resolved = data_dir / resolved
    return resolved


def artifacts_dir() -> Path:
    """Return the artifacts output directory."""
    p = project_root() / "artifacts"
    p.mkdir(parents=True, exist_ok=True)
    return p
