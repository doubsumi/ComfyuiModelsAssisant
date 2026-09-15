"""
提示词模板存储
==============
内置模板（只读）+ 用户模板（可读写）的合并查询。
"""
from __future__ import annotations

from typing import Optional

from backend.services.builtin_templates import get_builtin_templates
from backend.storage.preset_store import PresetStore


class PromptTemplateStore:
    def __init__(self, preset_store: PresetStore):
        self.preset_store = preset_store

    # ------------------------------------------------------------
    # 列表
    # ------------------------------------------------------------
    def list_all(self, ecosystem_id: str | None = None) -> list[dict]:
        """内置 + 用户模板合并。"""
        out = []
        out.extend(get_builtin_templates(ecosystem_id))
        for t in self.preset_store.list_user_templates():
            if ecosystem_id and t.get("ecosystemId") != ecosystem_id:
                continue
            out.append(t)
        # 按 ecosystemId 分组排序：内置在前
        out.sort(key=lambda x: (x.get("ecosystemId") or "", not x.get("builtin", False), x.get("name") or ""))
        return out

    def get(self, template_id: str) -> Optional[dict]:
        if template_id.startswith("builtin:"):
            for t in get_builtin_templates():
                if t["id"] == template_id:
                    return t
            return None
        return self.preset_store.get_user_template(template_id)

    # ------------------------------------------------------------
    # 用户模板写操作
    # ------------------------------------------------------------
    def save_user_template(self, payload: dict) -> dict:
        return self.preset_store.create_template(payload)

    def delete_user_template(self, template_id: str) -> bool:
        if template_id.startswith("builtin:"):
            return False
        return self.preset_store.delete_template(template_id)