"""扫描结果缓存"""
import time
from pathlib import Path
from backend.storage.json_store import JSONStore


class ScanCacheStore:
    def __init__(self, path: Path):
        self.store = JSONStore(
            path,
            default_factory=lambda: {"cachedAt": 0, "modelsDir": "", "files": []},
        )

    def get(self, models_dir: str, max_age: int) -> list | None:
        data = self.store.load()
        if data.get("modelsDir") != models_dir:
            return None
        if time.time() - data.get("cachedAt", 0) > max_age:
            return None
        return data.get("files", [])

    def set(self, models_dir: str, files: list) -> None:
        self.store.save({
            "cachedAt": time.time(),
            "modelsDir": models_dir,
            "files": files,
        })

    def invalidate(self) -> None:
        self.store.save({"cachedAt": 0, "modelsDir": "", "files": []})