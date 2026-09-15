"""
兼容性引擎
==========
判定一组模型文件是否可组合，并给出诊断报告。
"""
from __future__ import annotations

from typing import Optional

from backend.services.model_registry import ModelRegistry


# ============================================================
# 常量
# ============================================================
ROLE_ORDER = ["unet", "checkpoint", "encoder", "vae", "videoVae", "audioVae", "lora"]


# ============================================================
# 引擎
# ============================================================
class CompatibilityEngine:
    def __init__(self, registry: ModelRegistry):
        self.registry = registry

    # ------------------------------------------------------------
    # 主入口
    # ------------------------------------------------------------
    def check(self, selected_files: list[dict], scanned: list[dict]) -> dict:
        """主入口。返回兼容性报告。"""
        if not selected_files:
            return self._error("请至少选择一个模型文件")

        # 建立 scanned 索引（只取有注册信息的）
        scanned_index = {(m["file"], m["dir"]): m for m in scanned}

        # 分类用户勾选的文件
        classified: dict[str, list[dict]] = {r: [] for r in ROLE_ORDER}
        unknown: list[dict] = []
        for sel in selected_files:
            key = (sel["file"], sel["dir"])
            m = scanned_index.get(key)
            if m is None:
                unknown.append({"file": sel["file"], "dir": sel["dir"], "reason": "未在扫描结果中找到"})
                continue
            role = m.get("role", "unknown")
            if role in classified:
                classified[role].append(m)
            else:
                unknown.append({**m, "reason": f"未知角色 `{role}`"})

        # 处理主模型
        unets = classified["unet"]
        checkpoints = classified["checkpoint"]

        if len(unets) > 1:
            return {
                "ok": False,
                "needChoice": {
                    "role": "unet",
                    "candidates": [self._brief(m) for m in unets],
                    "reason": "选择了多个主模型，请只保留一个",
                },
                "resolved": {},
                "conflicts": [],
                "missing": [],
                "suggestions": [],
                "excluded": unknown,
            }

        if len(unets) == 0 and len(checkpoints) == 0:
            return self._error("请至少选择一个主模型（unet）或一体化底模（checkpoint）")
        if len(checkpoints) > 1:
            return {
                "ok": False,
                "needChoice": {
                    "role": "checkpoint",
                    "candidates": [self._brief(m) for m in checkpoints],
                    "reason": "选择了多个一体化底模，请只保留一个",
                },
                "resolved": {},
                "conflicts": [],
                "missing": [],
                "suggestions": [],
                "excluded": unknown,
            }

        primary = unets[0] if unets else checkpoints[0]
        is_checkpoint = len(unets) == 0

        # checkpoint 场景：不校验 encoder/vae，只用 LoRA 兼容性
        if is_checkpoint:
            return self._check_checkpoint(primary, classified, unknown)

        return self._check_unet(primary, classified, unknown, scanned)

    # ------------------------------------------------------------
    # checkpoint 场景
    # ------------------------------------------------------------
    def _check_checkpoint(self, primary: dict, classified: dict, unknown: list) -> dict:
        arch = primary.get("arch")
        compat_loras = primary.get("compatibleLoras") or []
        if not compat_loras and arch:
            compat_loras = [arch]

        loras_valid, loras_excluded = self._filter_loras(
            classified.get("lora", []), compat_loras
        )

        return {
            "ok": True,
            "primaryUnet": self._brief(primary),
            "needChoice": None,
            "resolved": {
                "checkpoint": self._brief(primary),
                "loras": [self._brief(m) for m in loras_valid],
            },
            "conflicts": [],
            "missing": [],
            "suggestions": [],
            "excluded": unknown + loras_excluded,
        }

    # ------------------------------------------------------------
    # unet 场景
    # ------------------------------------------------------------
    def _check_unet(
        self, primary: dict, classified: dict, unknown: list, scanned: list
    ) -> dict:
        conflicts: list[dict] = []
        missing: list[dict] = []
        suggestions: list[dict] = []
        excluded: list[dict] = list(unknown)

        primary_arch = primary.get("arch")
        compat_encoders = primary.get("compatibleEncoders") or []
        compat_vaes = primary.get("compatibleVaes") or []
        compat_loras = primary.get("compatibleLoras") or []

        # 检查必需字段是否齐全
        if not compat_encoders:
            missing.append({
                "role": "encoder",
                "reason": f"注册表中主模型 `{primary['file']}` 未定义 compatibleEncoders",
                "hint": "请先通过 Patch 更新补全",
            })
        if not compat_vaes:
            missing.append({
                "role": "vae",
                "reason": f"注册表中主模型 `{primary['file']}` 未定义 compatibleVaes",
                "hint": "请先通过 Patch 更新补全",
            })

        # 校验 encoder
        encoders_selected = classified.get("encoder", [])
        encoders_valid, encoders_excluded = self._filter_encoders(
            encoders_selected, compat_encoders, primary
        )

        if not encoders_valid and compat_encoders:
            # 尝试推荐
            recommended = self._suggest_encoder(primary, compat_encoders, scanned)
            missing.append({
                "role": "encoder",
                "reason": "未选择编码器",
                "candidates": compat_encoders,
            })
            if recommended:
                suggestions.append({
                    "role": "encoder",
                    "file": recommended["file"],
                    "reason": f"主模型 `{primary['file']}` 推荐使用此编码器",
                })
        elif len(encoders_valid) > 1:
            # 多个 encoder 都合法，但主模型通常只需要一个
            conflicts.append({
                "type": "multiple_encoders",
                "severity": "warning",
                "message": "选择了多个编码器，主模型通常只需要一个",
                "involvedFiles": [e["file"] for e in encoders_valid],
            })

        # 校验 vae
        vaes_selected = classified.get("vae", [])
        video_vaes_selected = classified.get("videoVae", [])
        audio_vaes_selected = classified.get("audioVae", [])
        all_vaes_selected = vaes_selected + video_vaes_selected + audio_vaes_selected

        vaes_valid, vaes_excluded = self._filter_vaes(
            all_vaes_selected, compat_vaes
        )

        # 检查 compat_vaes 里的每一项是否都有对应
        for required_vae in compat_vaes:
            matched = any(v["file"] == required_vae for v in vaes_valid)
            if not matched:
                # 从 scanned 里找候选
                candidate = self._find_scanned(scanned, required_vae)
                missing.append({
                    "role": "vae",
                    "reason": f"缺少必需的 VAE: `{required_vae}`",
                    "required": required_vae,
                    "available": bool(candidate),
                })

        # 校验 LoRA
        loras_selected = classified.get("lora", [])
        loras_valid, loras_excluded = self._filter_loras(
            loras_selected, compat_loras
        )

        # 处理未使用的 encoder / vae（用户勾了但不在白名单）
        for e in encoders_excluded:
            excluded.append({**e, "reason": "不在主模型的 compatibleEncoders 白名单中"})
        for v in vaes_excluded:
            excluded.append({**v, "reason": "不在主模型的 compatibleVaes 白名单中"})
        for l in loras_excluded:
            # entry = {k: v for k, v in l.items() if not k.startswith("_")}
            # entry["reason"] = l.get("_reason", "LoRA 不兼容")
            excluded.append(l)

                # 构建 resolved
        def _first_by_role(items: list[dict], role: str):
            for it in items:
                if it.get("role") == role:
                    return self._brief(it)
            return None

        resolved = {
            "unet":     self._brief(primary),
            "encoder":  self._brief(encoders_valid[0]) if encoders_valid else None,
            "vae":      _first_by_role(vaes_valid, "vae"),
            "videoVae": _first_by_role(vaes_valid, "videoVae"),
            "audioVae": _first_by_role(vaes_valid, "audioVae"),
            "loras":    [self._brief(m) for m in loras_valid],
        }

        # 判断整体 ok
        # LoRA 被排除也算失败——用户勾了但用不上，组合是不完整的
        has_excluded_lora = len(loras_excluded) > 0
        ok = (
            not missing
            and not has_excluded_lora
            and not any(c.get("severity") == "error" for c in conflicts)
        )

        return {
            "ok": ok,
            "primaryUnet": self._brief(primary),
            "needChoice": None,
            "resolved": resolved,
            "conflicts": conflicts,
            "missing": missing,
            "suggestions": suggestions,
            "excluded": excluded,
        }

    # ------------------------------------------------------------
    # 过滤辅助
    # ------------------------------------------------------------
    def _filter_encoders(
        self, selected: list[dict], whitelist: list[str], primary: dict
    ) -> tuple[list[dict], list[dict]]:
        valid, excluded = [], []
        required_type = (primary.get("encoderNodeParams") or {}).get("type")
        for m in selected:
            if m["file"] not in whitelist:
                excluded.append(m)
                continue
            # 如果有 required_type，校验 type 一致性
            if required_type:
                m_type = (m.get("encoderNodeParams") or {}).get("type")
                if m_type and m_type != required_type:
                    excluded.append({**m, "reason": f"编码器 type 不匹配：需要 {required_type}，实际 {m_type}"})
                    continue
            valid.append(m)
        return valid, excluded

    def _filter_vaes(
        self, selected: list[dict], whitelist: list[str]
    ) -> tuple[list[dict], list[dict]]:
        valid, excluded = [], []
        for m in selected:
            if m["file"] in whitelist:
                valid.append(m)
            else:
                excluded.append(m)
        return valid, excluded

    def _filter_loras(
        self, selected: list[dict], compat_archs: list[str]
    ) -> tuple[list[dict], list[dict]]:
        valid, excluded = [], []
        for m in selected:
            lora_arch = m.get("arch")
            if not lora_arch:
                excluded.append({**m, "reason": "LoRA 未定义 arch，无法判定兼容性"})
                continue
            if lora_arch in compat_archs:
                valid.append(m)
            else:
                excluded.append({**m, "reason": f"LoRA 架构 `{lora_arch}` 不在主模型兼容列表 {compat_archs} 中"})
        return valid, excluded

    # ------------------------------------------------------------
    # 推荐辅助
    # ------------------------------------------------------------
    def _suggest_encoder(
        self, primary: dict, whitelist: list[str], scanned: list[dict]
    ) -> Optional[dict]:
        """从白名单中挑一个优先级最高的编码器（必须是 scanned 中存在的）。"""
        scanned_by_file = {m["file"]: m for m in scanned}
        # 优先顺序：白名单靠前的
        for file_ in whitelist:
            if file_ in scanned_by_file:
                return scanned_by_file[file_]
        return None

    def _find_scanned(self, scanned: list[dict], file_name: str) -> Optional[dict]:
        for m in scanned:
            if m["file"] == file_name:
                return m
        return None

    # ------------------------------------------------------------
    # 输出精简
    # ------------------------------------------------------------
    def _brief(self, m: dict) -> dict:
        """精简输出，只保留前端需要的字段。"""
        return {
            "file": m.get("file"),
            "dir": m.get("dir"),
            "arch": m.get("arch"),
            "role": m.get("role"),
            "sizeBytes": m.get("sizeBytes"),
            "defaultWeight": m.get("defaultWeight"),
            "triggerWord": m.get("triggerWord"),
            "encoderNodeParams": m.get("encoderNodeParams"),
        }

    def _error(self, msg: str) -> dict:
        return {
            "ok": False,
            "primaryUnet": None,
            "needChoice": None,
            "resolved": {},
            "conflicts": [],
            "missing": [],
            "suggestions": [],
            "excluded": [],
            "error": msg,
        }