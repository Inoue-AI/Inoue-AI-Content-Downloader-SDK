from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path


class AbstractStorageBackend(ABC):
    """Base class that all storage backends must implement."""

    @abstractmethod
    async def upload(self, local_path: Path, key: str, mime_type: str) -> str:
        """Upload a file and return the resulting URL/path."""
        ...

    async def cleanup(self) -> None:
        """Optional cleanup hook for releasing resources."""
