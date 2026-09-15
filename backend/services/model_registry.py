"""
Model Registry 门面
===================
- 加载注册表 + 架构定义
- 查询接口
- 差异查询（unregistered / incomplete）
- Patch 合并入口
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from backend.services.patch_validator import validate_patch, merge_patch
from backend.services.prompt_builder import build_update_prompt
from backend.storage.patch_history import PatchHistory, compute_rollback
from backend.storage.registry_store import RegistryStore


class ModelRegistry:
    def __init__(
        self,
        registry_store: RegistryStore,
        architectures_path: Path,
        patches_dir: Path,
    ):
        self.store = registry_store
        self.architectures_path = Path(architectures_path)
        self.history = PatchHistory(patches_dir)
        self._architectures: Optional[dict] = None

    # ------------------------------------------------------------
    # 加载
    # ------------------------------------------------------------
    def load(self) -> dict:
        data = self.store.load()
        data["architectures"] = self._load_architectures()
        data["compatibilityMatrix"] = self._load_compatibility()
        return data

    def reload(self) -> dict:
        self.store.store.invalidate()
        self._architectures = None
        return self.load()

    def _load_architectures(self) -> dict:
        if self._architectures is None:
            import json
            if self.architectures_path.is_file():
                try:
                    blob = json.loads(self.architectures_path.read_text(encoding="utf-8"))
                    self._architectures = blob.get("architectures", {}) or {}
                except (OSError, Exception):
                    self._architectures = {}
            else:
                self._architectures = {}
        return self._architectures

    def _load_compatibility(self) -> dict:
        import json
        if self.architectures_path.is_file():
            try:
                blob = json.loads(self.architectures_path.read_text(encoding="utf-8"))
                return blob.get("compatibilityMatrix", {}) or {}
            except Exception:
                return {}
        return {}

    # ------------------------------------------------------------
    # 差异查询
    # ------------------------------------------------------------
    def get_unregistered(self, scanned: list[dict]) -> list[dict]:
        known = {(m["file"], m["dir"]) for m in self.store.load().get("models", [])}
        return [m for m in scanned if (m["file"], m["dir"]) not in known]

    def get_incomplete(self, scanned: list[dict]) -> list[dict]:
        """已注册但 needsLlm=True 的条目。"""
        known = {(m["file"], m["dir"]): m for m in self.store.load().get("models", [])}
        out = []
        for m in scanned:
            key = (m["file"], m["dir"])
            old = known.get(key)
            if old and old.get("needsLlm"):
                # 注册表字段优先（尤其是 source）
                merged = {**m, **old}
                # 用扫描结果刷新文件大小、mtime 等实时字段
                merged["sizeBytes"] = m.get("sizeBytes", merged.get("sizeBytes"))
                merged["mtime"] = m.get("mtime", merged.get("mtime"))
                out.append(merged)
        return out

    def get_patch_targets(self, scanned: list[dict]) -> list[dict]:
        """合并未注册 + 不完整，作为 Patch 更新的目标。"""
        unregistered = self.get_unregistered(scanned)
        incomplete = self.get_incomplete(scanned)
        seen = set()
        merged = []
        for m in unregistered + incomplete:
            key = (m["file"], m["dir"])
            if key in seen:
                continue
            seen.add(key)
            merged.append(m)
        return merged

    # ------------------------------------------------------------
    # 提示词
    # ------------------------------------------------------------
    def build_prompt(self, scanned: list[dict]) -> tuple[str, int]:
        targets = self.get_patch_targets(scanned)
        if not targets:
            return "", 0
        prompt = build_update_prompt(self.load(), targets)
        return prompt, len(targets)

    # ------------------------------------------------------------
    # Patch 合并
    # ------------------------------------------------------------
    def apply_patch(self, raw_patch: dict, scanned: list[dict]) -> dict:
        registry = self.store.load()
        registry["architectures"] = self._load_architectures()

        result = validate_patch(raw_patch, registry, scanned)

        if not result.valid:
            return {
                "ok": False,
                "error": "Patch 校验失败",
                "errors": [i.to_dict() for i in result.errors],
                "warnings": [i.to_dict() for i in result.warnings],
            }

        # 合并前移除临时注入的 architectures 字段（不写入 store）
        clean_registry = {
            "version": registry.get("version", "1.0.0"),
            "lastUpdated": registry.get("lastUpdated"),
            "models": registry.get("models", []),
        }

        new_registry, report = merge_patch(clean_registry, result.normalizedPatch)
        self.store.save(new_registry)

        # 保存历史
        patch_id = self.history.save(
            source_model=result.normalizedPatch.get("sourceModel", "unknown"),
            patch_version=result.normalizedPatch.get("patchVersion", "1.0.0"),
            added_count=report["added"],
            updated_count=report["updated"],
            diff=report["diff"],
        )

        return {
            "ok": True,
            "patchId": patch_id,
            "added": report["added"],
            "updated": report["updated"],
            "total": report["total"],
            "warnings": [i.to_dict() for i in result.warnings],
            "lastUpdated": new_registry["lastUpdated"],
        }

    # ------------------------------------------------------------
    # 历史 / 回滚
    # ------------------------------------------------------------
    def list_history(self, limit: int = 100) -> list[dict]:
        return self.history.list(limit)

    def rollback(self, patch_id: str) -> dict:
        record = self.history.load(patch_id)
        if record is None:
            return {"ok": False, "error": f"找不到 Patch: {patch_id}"}
        if record.rolledBack:
            return {"ok": False, "error": "该 Patch 已被回滚过"}

        registry = self.store.load()
        new_registry, report = compute_rollback(record, registry)
        self.store.save(new_registry)

        from datetime import datetime, timezone
        record.rolledBack = True
        record.rolledBackAt = datetime.now(timezone.utc).isoformat()
        self.history.update_record(record)

        return {
            "ok": True,
            "patchId": patch_id,
            "restored": report["restored"],
            "removed": report["removed"],
            "skipped": report["skipped"],
            "errors": report.get("errors", []),
        }

    def prune_history(self, keep: int) -> int:
        return self.history.prune(keep)