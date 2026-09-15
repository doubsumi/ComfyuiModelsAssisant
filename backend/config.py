"""配置管理"""
from pathlib import Path
from backend.storage.json_store import JSONStore


DEFAULT_CONFIG = {
    "modelsDir": r"E:\ComfyUI_windows_portable_nvidia\ComfyUI_windows_portable\ComfyUI\models",
    "comfyuiRoot": r"E:\ComfyUI_windows_portable_nvidia\ComfyUI_windows_portable\ComfyUI",
    "port": 17890,
    "confidenceThreshold": 0.6,
    "scanCacheMaxAge": 300,
    "patchHistoryRetention": 100,
}


class Config:
    def __init__(self, data_dir: Path):
        self.store = JSONStore(
            data_dir / "config.json",
            default_factory=lambda: dict(DEFAULT_CONFIG),
        )
        self._data = None

    @property
    def data(self) -> dict:
        if self._data is None:
            self._data = {**DEFAULT_CONFIG, **self.store.load()}
        return self._data

    def get(self, key: str, default=None):
        return self.data.get(key, default)

    def update(self, patch: dict) -> dict:
        for k in patch:
            if k not in DEFAULT_CONFIG:
                raise ValueError(f"未知配置项: {k}")
        self._data = {**self.data, **patch}
        self.store.save(self._data)
        return self._data

    def reset(self) -> dict:
        self._data = dict(DEFAULT_CONFIG)
        self.store.save(self._data)
        return self._data