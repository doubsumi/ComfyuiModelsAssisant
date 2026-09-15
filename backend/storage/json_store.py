"""JSON 原子读写"""
import json
import os
import tempfile
from pathlib import Path
from typing import Any, Callable


class JSONStore:
    def __init__(self, path: Path, default_factory: Callable[[], Any] | None = None):
        self.path = Path(path)
        self.default_factory = default_factory or (lambda: {})
        self._cache = None

    def load(self) -> Any:
        if self._cache is not None:
            return self._cache
        if not self.path.exists():
            self._cache = self.default_factory()
            return self._cache
        try:
            text = self.path.read_text(encoding="utf-8")
            self._cache = json.loads(text) if text.strip() else self.default_factory()
        except (OSError, json.JSONDecodeError) as e:
            raise RuntimeError(f"无法读取 {self.path}: {e}")
        return self._cache

    def save(self, data: Any) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(prefix=self.path.name + ".", dir=str(self.path.parent))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            os.replace(tmp, self.path)
        except Exception:
            if os.path.exists(tmp):
                os.unlink(tmp)
            raise
        self._cache = data

    def invalidate(self) -> None:
        self._cache = None