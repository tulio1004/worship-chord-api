"""Safe temporary file handling utilities."""

import tempfile
import shutil
import logging
from pathlib import Path
from contextlib import contextmanager
from typing import Generator

from app.core.config import settings

logger = logging.getLogger(__name__)


def ensure_temp_dir() -> Path:
    """Ensure the configured temp directory exists."""
    path = Path(settings.temp_dir)
    path.mkdir(parents=True, exist_ok=True)
    return path


@contextmanager
def temp_workspace() -> Generator[Path, None, None]:
    """
    Context manager that creates a unique temporary directory,
    yields the path, then cleans it up on exit.
    """
    workspace = Path(tempfile.mkdtemp(prefix="worship_", dir=ensure_temp_dir()))
    logger.debug(f"Created temp workspace: {workspace}")
    try:
        yield workspace
    finally:
        try:
            shutil.rmtree(workspace, ignore_errors=True)
            logger.debug(f"Cleaned temp workspace: {workspace}")
        except Exception as e:
            logger.warning(f"Failed to clean temp workspace {workspace}: {e}")


def safe_delete(path: Path) -> None:
    """Delete a file or directory without raising."""
    try:
        if path.is_file():
            path.unlink()
        elif path.is_dir():
            shutil.rmtree(path)
    except Exception as e:
        logger.warning(f"Could not delete {path}: {e}")
