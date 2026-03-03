from __future__ import annotations

import asyncio
import shutil
import tempfile
from pathlib import Path
from types import TracebackType


class AsyncTempDir:
    """Async context manager for temporary directories with guaranteed cleanup."""

    def __init__(self, base_dir: str | None = None) -> None:
        self._base_dir = base_dir
        self._path: Path | None = None

    async def __aenter__(self) -> Path:
        self._path = Path(await asyncio.to_thread(tempfile.mkdtemp, dir=self._base_dir))
        return self._path

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        if self._path and self._path.exists():
            await asyncio.to_thread(shutil.rmtree, str(self._path), True)
