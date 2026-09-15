"""
Patch 校验器
============
校验 LLM 生成的 Patch，输出规范化后的 Patch。
- 校验失败返回带上下文的 issues 列表
- 校验通过返回 normalized patch（可直接合并）
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional


VALID_ROLES = {"unet", "encoder", "vae", "videoVae", "audioVae", "lora", "checkpoint"}
MISSING_FIELD_FALLBACK = "needs_llm"


# ============================================================
# 数据类
# ============================================================
@dataclass
class Issue:
    level: str                          # "error" | "warning" | "info"
    modelIndex: Optional[int] = None
    field: Optional[str] = None
    message: str = ""
    suggestion: Optional[str] = None

    def to_dict(self) -> dict:
        d = {"level": self.level, "message": self.message}
        if self.modelIndex is not None:
            d["index"] = self.modelIndex
        if self.field:
            d["field"] = self.field
        if self.suggestion:
            d["suggestion"] = self.suggestion
        return d


@dataclass
class ValidationResult:
    valid: bool
    issues: list = field(default_factory=list)
    normalizedPatch: Optional[dict] = None

    @property
    def errors(self) -> list[Issue]:
        return [i for i in self.issues if i.level == "error"]

    @property
    def warnings(self) -> list[Issue]:
        return [i for i in self.issues if i.level == "warning"]


# ============================================================
# 主校验
# ============================================================
def validate_patch(
    patch: Any,
    registry: dict,
    scanned_entries: list[dict],
) -> ValidationResult:
    issues: list[Issue] = []

    # ---- 1. 顶层结构 ----
    if not isinstance(patch, dict):
        issues.append(Issue("error", message="Patch 必须是 JSON 对象"))
        return ValidationResult(False, issues)

    registry_version = registry.get("version", "1.0.0")
    patch_version = patch.get("patchVersion")
    if patch_version != registry_version:
        issues.append(Issue(
            "error", field="patchVersion",
            message=f"版本不匹配：patch={patch_version}, registry={registry_version}",
            suggestion=f"请让 LLM 重新生成 patchVersion 为 {registry_version} 的 Patch",
        ))

    models = patch.get("models")
    if not isinstance(models, list):
        issues.append(Issue(
            "error", field="models",
            message="`models` 必须是数组",
        ))
        return ValidationResult(False, issues)

    if not models:
        issues.append(Issue("warning", message="Patch 中没有任何模型条目"))

    # ---- 2. 扫描索引 ----
    scanned_keys = {(m["file"], m["dir"]) for m in scanned_entries}

    # ---- 3. 架构白名单 ----
    valid_archs = set((registry.get("architectures") or {}).keys())

    # ---- 4. 逐条校验 ----
    normalized_models: list[dict] = []
    for idx, raw in enumerate(models):
        entry_issues, normalized = _validate_single(raw, idx, valid_archs, scanned_keys)
        issues.extend(entry_issues)
        if normalized is not None:
            normalized_models.append(normalized)

    # ---- 5. 判定 ----
    has_error = any(i.level == "error" for i in issues)
    if has_error:
        return ValidationResult(False, issues, None)

    normalized_patch = {
        "patchVersion": registry_version,
        "source": patch.get("source", "llm"),
        "sourceModel": patch.get("sourceModel", "unknown"),
        "timestamp": patch.get("timestamp", datetime.now(timezone.utc).isoformat()),
        "models": normalized_models,
    }
    return ValidationResult(True, issues, normalized_patch)


def _validate_single(
    raw: Any,
    idx: int,
    valid_archs: set[str],
    scanned_keys: set[tuple[str, str]],
) -> tuple[list[Issue], Optional[dict]]:
    issues: list[Issue] = []

    if not isinstance(raw, dict):
        issues.append(Issue("error", modelIndex=idx, message="条目必须是对象"))
        return issues, None

    file_ = raw.get("file")
    dir_ = raw.get("dir")

    # 必填字段
    if not file_ or not isinstance(file_, str):
        issues.append(Issue("error", modelIndex=idx, field="file", message="缺少 file 字段"))
        return issues, None
    if not dir_ or not isinstance(dir_, str):
        issues.append(Issue("error", modelIndex=idx, field="dir", message="缺少 dir 字段"))
        return issues, None

    # 必须是扫描到的真实文件
    if (file_, dir_) not in scanned_keys:
        issues.append(Issue(
            "error", modelIndex=idx, field="file",
            message=f"文件 `{dir_}/{file_}` 不在扫描结果中",
            suggestion="请确认文件是否已下载到 ComfyUI 的 models 目录",
        ))
        return issues, None

    # arch（允许 null）
    arch = raw.get("arch")
    if arch is not None:
        if not isinstance(arch, str):
            issues.append(Issue("error", modelIndex=idx, field="arch", message="arch 必须是字符串或 null"))
            return issues, None
        if arch not in valid_archs:
            issues.append(Issue(
                "error", modelIndex=idx, field="arch",
                message=f"未注册的架构 `{arch}`",
                suggestion=f"可用架构: {sorted(valid_archs)}",
            ))
            return issues, None

    # role
    role = raw.get("role", "unknown")
    if role not in VALID_ROLES:
        issues.append(Issue(
            "error", modelIndex=idx, field="role",
            message=f"非法 role `{role}`",
            suggestion=f"允许值: {sorted(VALID_ROLES)}",
        ))
        return issues, None

    # 条件字段校验（warning 级别）
    if role == "unet":
        ce = raw.get("compatibleEncoders")
        cv = raw.get("compatibleVaes")
        if not ce or not isinstance(ce, list):
            issues.append(Issue(
                "warning", modelIndex=idx, field="compatibleEncoders",
                message="unet 建议提供 compatibleEncoders",
            ))
        if not cv or not isinstance(cv, list):
            issues.append(Issue(
                "warning", modelIndex=idx, field="compatibleVaes",
                message="unet 建议提供 compatibleVaes",
            ))

    if role == "encoder":
        params = raw.get("encoderNodeParams")
        if not isinstance(params, dict) or "type" not in params:
            issues.append(Issue(
                "warning", modelIndex=idx, field="encoderNodeParams",
                message="encoder 建议提供 encoderNodeParams.type",
                suggestion='例如 {"type": "krea2"}',
            ))

    if role == "lora":
        dw = raw.get("defaultWeight")
        if dw is not None:
            if not isinstance(dw, (int, float)):
                issues.append(Issue(
                    "warning", modelIndex=idx, field="defaultWeight",
                    message="defaultWeight 必须是数字，将被忽略",
                ))
            elif not (0.0 <= float(dw) <= 2.0):
                issues.append(Issue(
                    "warning", modelIndex=idx, field="defaultWeight",
                    message=f"defaultWeight={dw} 超出 [0.0, 2.0]，将裁剪到合法范围",
                ))

    # 构建规范化条目
    normalized = {
        "file": file_,
        "dir": dir_,
        "arch": arch,
        "role": role,
        "source": "llm_patch",
        "needsLlm": False,
    }

    for k in ("compatibleEncoders", "compatibleVaes", "compatibleLoras"):
        v = raw.get(k)
        if isinstance(v, list) and v:
            normalized[k] = v

    params = raw.get("encoderNodeParams")
    if isinstance(params, dict) and params:
        normalized["encoderNodeParams"] = params

    tw = raw.get("triggerWord")
    if isinstance(tw, str) and tw:
        normalized["triggerWord"] = tw

    dw = raw.get("defaultWeight")
    if isinstance(dw, (int, float)):
        normalized["defaultWeight"] = max(0.0, min(2.0, float(dw)))

    dp = raw.get("defaultParams")
    if isinstance(dp, dict) and dp:
        normalized["defaultParams"] = dp

    if raw.get("_note"):
        normalized["_note"] = str(raw["_note"])

    return issues, normalized


# ============================================================
# 合并
# ============================================================
OVERWRITABLE = {
    "arch", "role",
    "compatibleEncoders", "compatibleVaes", "compatibleLoras",
    "defaultParams", "encoderNodeParams",
    "triggerWord", "defaultWeight",
}

FILLABLE = {
    "triggerWord", "defaultWeight", "encoderNodeParams",
    "compatibleEncoders", "compatibleVaes", "compatibleLoras",
}


def merge_patch(registry: dict, normalized_patch: dict) -> tuple[dict, dict]:
    """
    字段级合并。返回 (new_registry, report)。
    report = { added, updated, total, diff }
    diff 用于回滚。
    """
    existing = {(m["file"], m["dir"]): m for m in registry.get("models", [])}
    added = 0
    updated = 0
    diff: list[dict] = []

    for new_m in normalized_patch["models"]:
        key = (new_m["file"], new_m["dir"])
        old = existing.get(key)

        if old is None:
            existing[key] = new_m
            added += 1
            diff.append({
                "file": new_m["file"],
                "dir": new_m["dir"],
                "action": "added",
                "changes": {},
            })
            continue

        changes: dict[str, dict] = {}
        old_source = old.get("source", "heuristic")

        if old_source in ("heuristic", "unknown"):
            # 覆盖式合并
            for k in OVERWRITABLE:
                if k in new_m and new_m[k] is not None:
                    old_val = old.get(k)
                    if old_val != new_m[k]:
                        changes[k] = {"old": old_val, "new": new_m[k]}
                        old[k] = new_m[k]
            if old_source != "llm_patch":
                changes["source"] = {"old": old_source, "new": "llm_patch"}
                old["source"] = "llm_patch"
            if old.get("confidence", 0) < 1.0:
                changes["confidence"] = {"old": old.get("confidence", 0), "new": 1.0}
                old["confidence"] = 1.0
            if old.get("needsLlm"):
                changes["needsLlm"] = {"old": True, "new": False}
                old["needsLlm"] = False
        else:
            # 只填充缺失字段
            for k in FILLABLE:
                if k in new_m and new_m[k] is not None and not old.get(k):
                    changes[k] = {"old": old.get(k), "new": new_m[k]}
                    old[k] = new_m[k]

        if changes:
            updated += 1
            diff.append({
                "file": old["file"],
                "dir": old["dir"],
                "action": "updated",
                "changes": changes,
            })

    registry["models"] = list(existing.values())
    registry["lastUpdated"] = datetime.now(timezone.utc).isoformat()

    report = {
        "added": added,
        "updated": updated,
        "total": len(registry["models"]),
        "diff": diff,
    }
    return registry, report