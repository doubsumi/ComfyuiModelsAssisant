"""
预设 + 用户模板存储
==================
共用 presets.json：
{
  "version": "1.0.0",
  "presets": [...],
  "templates": [...]
}
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from backend.storage.json_store import JSONStore


class PresetStore:
    def __init__(self, path: Path):
        self.store = JSONStore(path, default_factory=self._empty)

    def _empty(self) -> dict:
        return {
            "version": "1.0.0",
            "presets": [],
            "templates": [],
        }

    # ------------------------------------------------------------
    # 预设 CRUD
    # ------------------------------------------------------------
    def list_presets(self) -> list[dict]:
        return self.store.load().get("presets", [])

    def get_preset(self, preset_id: str) -> Optional[dict]:
        for p in self.list_presets():
            if p["id"] == preset_id:
                return p
        return None

    def create_preset(self, payload: dict) -> dict:
        now = datetime.now(timezone.utc).isoformat()
        preset = {
            "id": str(uuid.uuid4()),
            "name": (payload.get("name") or "").strip() or "未命名预设",
            "createdAt": now,
            "updatedAt": now,
            "ecosystemId": payload.get("ecosystemId"),
            "models": payload.get("models") or {},
            "modelDirs": payload.get("modelDirs") or {},
            "loras": payload.get("loras") or [],
            "params": payload.get("params") or {},
            "prompt": payload.get("prompt") or {"positive": "", "negative": "", "videoPrompt": ""},
        }
        data = self.store.load()
        data.setdefault("presets", []).append(preset)
        self.store.save(data)
        return preset

    def update_preset(self, preset_id: str, patch: dict) -> Optional[dict]:
        data = self.store.load()
        for p in data.get("presets", []):
            if p["id"] != preset_id:
                continue
            for k in ("name", "ecosystemId", "models", "modelDirs", "loras", "params", "prompt"):
                if k in patch:
                    p[k] = patch[k]
            p["updatedAt"] = datetime.now(timezone.utc).isoformat()
            self.store.save(data)
            return p
        return None

    def delete_preset(self, preset_id: str) -> bool:
        data = self.store.load()
        before = len(data.get("presets", []))
        data["presets"] = [p for p in data.get("presets", []) if p["id"] != preset_id]
        if len(data["presets"]) == before:
            return False
        self.store.save(data)
        return True

    # ------------------------------------------------------------
    # 用户模板 CRUD
    # ------------------------------------------------------------
    def list_user_templates(self) -> list[dict]:
        return self.store.load().get("templates", [])

    def get_user_template(self, template_id: str) -> Optional[dict]:
        for t in self.list_user_templates():
            if t["id"] == template_id:
                return t
        return None

    def create_template(self, payload: dict) -> dict:
        now = datetime.now(timezone.utc).isoformat()
        template = {
            "id": str(uuid.uuid4()),
            "ecosystemId": payload.get("ecosystemId"),
            "name": (payload.get("name") or "").strip() or "未命名模板",
            "builtin": False,
            "tags": payload.get("tags") or [],
            "positive": payload.get("positive") or "",
            "negative": payload.get("negative") or "",
            "videoPrompt": payload.get("videoPrompt") or "",
            "notes": payload.get("notes") or "",
            "createdAt": now,
        }
        data = self.store.load()
        data.setdefault("templates", []).append(template)
        self.store.save(data)
        return template

    def delete_template(self, template_id: str) -> bool:
        data = self.store.load()
        before = len(data.get("templates", []))
        data["templates"] = [t for t in data.get("templates", []) if t["id"] != template_id]
        if len(data["templates"]) == before:
            return False
        self.store.save(data)
        return True