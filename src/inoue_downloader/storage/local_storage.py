from __future__ import annotations

import asyncio
import logging
import shutil
from pathlib import Path

from .base import AbstractStorageBackend

logger = logging.getLogger(__name__)


class LocalStorageBackend(AbstractStorageBackend):
    """Storage backend that saves files to the local filesystem."""

    def __init__(self, output_dir: str) -> None:
        self._output_dir = Path(output_dir)

    async def upload(self, local_path: Path, key: str, mime_type: str) -> str:
        dest = self._output_dir / key
        await asyncio.to_thread(self._copy_file, local_path, dest)
        logger.info("Saved %s to %s", local_path.name, dest)
        return str(dest)

    @staticmethod
    def _copy_file(src: Path, dest: Path) -> None:
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
