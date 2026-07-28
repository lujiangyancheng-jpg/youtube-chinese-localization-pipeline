from __future__ import annotations

from pathlib import Path
from typing import Any

from ..utils.files import atomic_write_json, load_json
from ..utils.hashing import stable_hash


class TranslationCache:
    def __init__(self, directory: Path) -> None:
        self.directory = directory
        self.directory.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def key(payload: Any) -> str:
        return stable_hash(payload)

    def get(self, key: str) -> Any | None:
        path = self.directory / f"{key}.json"
        return load_json(path) if path.is_file() else None

    def put(self, key: str, value: Any) -> Path:
        path = self.directory / f"{key}.json"
        atomic_write_json(path, value)
        return path
