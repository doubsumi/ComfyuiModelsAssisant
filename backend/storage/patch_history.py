"""
Patch 历史记录
==============
- 每次成功合并 Patch 后写入一个快照文件（含 diff）
- 支持整体回滚到某个 Patch 应用前的状态
- 保留策略：永久保留（用户可在设置里手动清理）
"""
from __future__ import annotations

import json
import secrets
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional


@dataclass
class PatchRecord:
    patchId: str
    appliedAt: str
    sourceModel: str
    patchVersion: str
    addedCount: int
    updatedCount: int
    rolledBack: bool = False
    rolledBackAt: Optional[str] = None
    # diff: [{ file, dir, action: "added"|"updated", changes: { field: { old, new } } }]
    diff: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "patchId": self.patchId,
            "appliedAt": self.appliedAt,
            "sourceModel": self.sourceModel,
            "patchVersion": self.patchVersion,
            "addedCount": self.addedCount,
            "updatedCount": self.updatedCount,
            "rolledBack": self.rolledBack,
            "rolledBackAt": self.rolledBackAt,
            "diff": self.diff,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "PatchRecord":
        return cls(
            patchId=d["patchId"],
            appliedAt=d["appliedAt"],
            sourceModel=d.get("sourceModel", "unknown"),
            patchVersion=d.get("patchVersion", "1.0.0"),
            addedCount=d.get("addedCount", 0),
            updatedCount=d.get("updatedCount", 0),
            rolledBack=d.get("rolledBack", False),
            rolledBackAt=d.get("rolledBackAt"),
            diff=d.get("diff", []),
        )


class PatchHistory:
    def __init__(self, patches_dir: Path):
        self.patches_dir = Path(patches_dir)
        self.patches_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------
    # 保存
    # ------------------------------------------------------------
    def save(
        self,
        source_model: str,
        patch_version: str,
        added_count: int,
        updated_count: int,
        diff: list[dict],
    ) -> str:
        patch_id = self._make_patch_id()
        record = PatchRecord(
            patchId=patch_id,
            appliedAt=datetime.now(timezone.utc).isoformat(),
            sourceModel=source_model,
            patchVersion=patch_version,
            addedCount=added_count,
            updatedCount=updated_count,
            diff=diff,
        )
        path = self.patches_dir / f"{patch_id}.json"
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(
            json.dumps(record.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        tmp.replace(path)
        return patch_id

    def _make_patch_id(self) -> str:
        ts = datetime.now().strftime("%Y%m%d-%H%M%S")
        return f"{ts}-{secrets.token_hex(3)}"

    # ------------------------------------------------------------
    # 查询
    # ------------------------------------------------------------
    def list(self, limit: int = 100) -> list[dict]:
        items = []
        for path in sorted(self.patches_dir.glob("*.json"), reverse=True):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                items.append({
                    "patchId": data["patchId"],
                    "appliedAt": data["appliedAt"],
                    "sourceModel": data.get("sourceModel", "unknown"),
                    "patchVersion": data.get("patchVersion", "1.0.0"),
                    "addedCount": data.get("addedCount", 0),
                    "updatedCount": data.get("updatedCount", 0),
                    "rolledBack": data.get("rolledBack", False),
                    "rolledBackAt": data.get("rolledBackAt"),
                })
                if len(items) >= limit:
                    break
            except (OSError, json.JSONDecodeError, KeyError):
                continue
        return items

    def load(self, patch_id: str) -> Optional[PatchRecord]:
        path = self.patches_dir / f"{patch_id}.json"
        if not path.is_file():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return PatchRecord.from_dict(data)
        except (OSError, json.JSONDecodeError):
            return None

    def update_record(self, record: PatchRecord) -> None:
        path = self.patches_dir / f"{record.patchId}.json"
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(
            json.dumps(record.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        tmp.replace(path)

    # ------------------------------------------------------------
    # 清理
    # ------------------------------------------------------------
    def prune(self, keep: int) -> int:
        """保留最近 keep 条，删除更早的（不删已回滚的记录）。返回删除数量。"""
        files = sorted(self.patches_dir.glob("*.json"), reverse=True)
        removed = 0
        for path in files[keep:]:
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                if data.get("rolledBack"):
                    continue
                path.unlink()
                removed += 1
            except (OSError, json.JSONDecodeError):
                continue
        return removed


# ============================================================
# 回滚
# ============================================================
def compute_rollback(record: PatchRecord, registry: dict) -> tuple[dict, dict]:
    """
    根据 Patch 的 diff，计算回滚操作。
    返回 (new_registry, rollback_report)
    """
    models_by_key = {(m["file"], m["dir"]): m for m in registry.get("models", [])}
    report = {"restored": 0, "removed": 0, "skipped": 0, "errors": []}

    for entry in record.diff:
        key = (entry["file"], entry["dir"])
        action = entry["action"]

        if action == "added":
            if key in models_by_key:
                del models_by_key[key]
                report["removed"] += 1
            else:
                report["skipped"] += 1
        elif action == "updated":
            old = models_by_key.get(key)
            if old is None:
                report["skipped"] += 1
                report["errors"].append(
                    f"{entry['dir']}/{entry['file']} 已不存在，跳过"
                )
                continue
            for field_name, change in entry.get("changes", {}).items():
                old_value = change.get("old")
                if old_value is None:
                    old.pop(field_name, None)
                else:
                    old[field_name] = old_value
            report["restored"] += 1

    registry["models"] = list(models_by_key.values())
    return registry, report