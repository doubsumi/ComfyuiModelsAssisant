"""注册表持久化"""
from pathlib import Path
from backend.storage.json_store import JSONStore


REGISTRY_VERSION = "1.0.0"


class RegistryStore:
    def __init__(self, path: Path):
        self.store = JSONStore(path, default_factory=self._empty)

    def _empty(self) -> dict:
        return {
            "version": REGISTRY_VERSION,
            "lastUpdated": None,
            "models": [],
        }

    def load(self) -> dict:
        return self.store.load()

    def save(self, data: dict) -> None:
        self.store.save(data)