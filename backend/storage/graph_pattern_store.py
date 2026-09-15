"""
图谱模式存储
============
- 加载 builtin + custom 目录
- 同名 ID 时 custom 覆盖 builtin
- 提供 list / get 接口
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional


class GraphPatternStore:
    def __init__(self, patterns_root: Path):
        self.root = Path(patterns_root)
        self.builtin_dir = self.root / "builtin"
        self.custom_dir = self.root / "custom"
        self.builtin_dir.mkdir(parents=True, exist_ok=True)
        self.custom_dir.mkdir(parents=True, exist_ok=True)
        self._cache: Optional[dict[str, dict]] = None

    # ------------------------------------------------------------
    # 加载
    # ------------------------------------------------------------
    def _load_all(self) -> dict[str, dict]:
        patterns: dict[str, dict] = {}
        for d in (self.builtin_dir, self.custom_dir):
            for path in sorted(d.glob("*.json")):
                try:
                    data = json.loads(path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError) as e:
                    print(f"[patterns] 无法加载 {path}: {e}")
                    continue
                pid = data.get("id")
                if not pid:
                    print(f"[patterns] 缺少 id 字段: {path}")
                    continue
                data["_source"] = "custom" if d == self.custom_dir else "builtin"
                data["_path"] = str(path)
                patterns[pid] = data
        return patterns

    def reload(self) -> None:
        self._cache = None

    def _patterns(self) -> dict[str, dict]:
        if self._cache is None:
            self._cache = self._load_all()
        return self._cache

    # ------------------------------------------------------------
    # 查询
    # ------------------------------------------------------------
    def list(self) -> list[dict]:
        """返回所有 pattern 的摘要信息。"""
        out = []
        for pid, p in self._patterns().items():
            out.append({
                "id": pid,
                "label": p.get("label", pid),
                "category": p.get("category", "image"),
                "compatibleArchitectures": p.get("compatibleArchitectures", []),
                "source": p.get("_source", "builtin"),
                "pluginDependencies": p.get("pluginDependencies", []),
            })
        out.sort(key=lambda x: (x["category"], x["id"]))
        return out

    def get(self, pattern_id: str) -> Optional[dict]:
        return self._patterns().get(pattern_id)

    def find_by_architecture(self, arch: str) -> list[dict]:
        """找出兼容指定架构的所有 pattern。"""
        out = []
        for p in self._patterns().values():
            if arch in (p.get("compatibleArchitectures") or []):
                out.append(p)
        return out