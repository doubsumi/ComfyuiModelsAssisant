"""
生态推荐器
=========
从已注册模型推荐可用生态。按 family 合并（如 minimax_h3_fl2va 和 ref2va 归为 MiniMax H3）。

关键设计：
- unet / checkpoint 按 (arch, role) 索引
- encoder / vae 按 architectures.json 声明的文件名查找（跨 arch 复用）
- lora 按 compatibilityMatrix[arch].compatibleLoras 匹配
"""
from __future__ import annotations

from backend.storage.graph_pattern_store import GraphPatternStore


ARCH_FAMILIES = {
    "minimax_h3": {
        "label": "MiniMax H3",
        "members": ["minimax_h3_fl2va", "minimax_h3_ref2va"],
    },
}


PLATFORM_LINKS = [
    {"name": "ComfyUI 官方模板", "url": "https://github.com/Comfy-Org/workflow_templates"},
    {"name": "OpenArt Workflows", "url": "https://openart.ai/workflows"},
    {"name": "Comfy Workflows", "url": "https://comfyworkflows.com/"},
    {"name": "Civitai", "url": "https://civitai.com/"},
    {"name": "LiblibAI", "url": "https://www.liblib.art/"},
]


class EcosystemRecommender:
    def __init__(self, registry, pattern_store: GraphPatternStore):
        self.registry = registry
        self.pattern_store = pattern_store

    # ------------------------------------------------------------
    # 主入口
    # ------------------------------------------------------------
    def recommend(self, scanned: list[dict]) -> dict:
        registry_data = self.registry.store.load()
        architectures = registry_data.get("architectures", {}) or {}
        compatibility = registry_data.get("compatibilityMatrix", {}) or {}
        registry_models = {
            (m["file"], m["dir"]): m
            for m in registry_data.get("models", [])
        }

        # 1. 合并 scanned + registry
        merged_models: list[dict] = []
        for m in scanned:
            key = (m["file"], m["dir"])
            reg = registry_models.get(key, {})
            merged_models.append({**m, **reg})

        # 2. 按文件名索引（用于 encoder / vae 查找，支持跨 arch 复用）
        by_filename: dict[str, dict] = {}
        for m in merged_models:
            fname = m.get("file")
            if not fname:
                continue
            # 同一个文件名优先取 needsLlm=False 的版本（已补全）
            exist = by_filename.get(fname)
            if exist is None or (exist.get("needsLlm") and not m.get("needsLlm")):
                by_filename[fname] = m

        # 3. 按 (arch, role) 索引（用于 unet / checkpoint）
        by_arch_role: dict[tuple, list[dict]] = {}
        for m in merged_models:
            arch = m.get("arch")
            role = m.get("role")
            if arch and role:
                by_arch_role.setdefault((arch, role), []).append(m)

        # 4. 图谱索引
        pattern_by_arch: dict[str, dict] = {}
        for p in self.pattern_store.list():
            for a in p.get("compatibleArchitectures", []):
                pattern_by_arch[a] = p

        # 5. 按 family 分组有 unet 的 arch
        families: dict[str, list[str]] = {}
        for arch, arch_def in architectures.items():
            unets = by_arch_role.get((arch, "unet"), [])
            checkpoints = by_arch_role.get((arch, "checkpoint"), [])
            if not unets and not checkpoints:
                continue
            fid = self._find_family(arch)
            families.setdefault(fid, []).append(arch)

        # 6. 构建 ecosystem 列表
        ecosystems = []
        for family_id, member_arches in families.items():
            variants = []
            all_encoders: list[dict] = []
            all_vaes: list[dict] = []
            all_loras: list[dict] = []
            seen_enc, seen_vae, seen_lora = set(), set(), set()

            for arch in member_arches:
                arch_def = architectures.get(arch, {})
                unets = by_arch_role.get((arch, "unet"), [])
                checkpoints = by_arch_role.get((arch, "checkpoint"), [])

                # --- encoder 候选：按 arch_def.encoders 声明的文件名查找 ---
                encoder_files = arch_def.get("encoders") or []
                encoder_candidates: list[dict] = []
                for fname in encoder_files:
                    m = by_filename.get(fname)
                    if m:
                        encoder_candidates.append(m)
                        k = (m["file"], m.get("dir"))
                        if k not in seen_enc:
                            seen_enc.add(k)
                            all_encoders.append(self._brief(m))

                # --- vae 候选：按 arch_def.vae 声明 ---
                vae_field = arch_def.get("vae")
                if isinstance(vae_field, list):
                    vae_files = vae_field
                elif vae_field:
                    vae_files = [vae_field]
                else:
                    vae_files = []
                vae_candidates: list[dict] = []
                for fname in vae_files:
                    m = by_filename.get(fname)
                    if m:
                        vae_candidates.append(m)
                        k = (m["file"], m.get("dir"))
                        if k not in seen_vae:
                            seen_vae.add(k)
                            all_vaes.append(self._brief(m))

                # --- lora 候选：按 compatibilityMatrix ---
                compat = compatibility.get(arch, {})
                compat_lora_archs = compat.get("compatibleLoras") or []
                lora_candidates: list[dict] = []
                for m in merged_models:
                    if m.get("role") != "lora":
                        continue
                    if m.get("arch") not in compat_lora_archs:
                        continue
                    lora_candidates.append(m)
                    k = (m["file"], m.get("dir"))
                    if k not in seen_lora:
                        seen_lora.add(k)
                        all_loras.append(self._brief(m))

                # --- 判定状态 ---
                missing = []
                if encoder_files and not encoder_candidates:
                    missing.append("encoder")
                if vae_files and not vae_candidates:
                    missing.append("vae")

                pattern = pattern_by_arch.get(arch)
                has_pattern = pattern is not None

                if missing:
                    status = "missing"
                elif not has_pattern:
                    status = "no-pattern"
                else:
                    status = "available"

                variants.append({
                    "arch": arch,
                    "label": arch_def.get("label", arch),
                    "status": status,
                    "hasPattern": has_pattern,
                    "patternId": pattern["id"] if pattern else None,
                    "unetCandidates": [self._brief(m) for m in unets],
                    "checkpointCandidates": [self._brief(m) for m in checkpoints],
                    "encoderCandidates": [self._brief(m) for m in encoder_candidates],
                    "vaeCandidates": [self._brief(m) for m in vae_candidates],
                    "loraCandidates": [self._brief(m) for m in lora_candidates],
                    "missing": missing,
                })

            # family 汇总状态：取最优
            statuses = [v["status"] for v in variants]
            if "available" in statuses:
                family_status = "available"
            elif "no-pattern" in statuses:
                family_status = "no-pattern"
            else:
                family_status = "missing"

            ecosystems.append({
                "familyId": family_id,
                "label": self._family_label(family_id, architectures),
                "status": family_status,
                "variants": variants,
                "encoderCandidates": all_encoders,
                "vaeCandidates": all_vaes,
                "loraCandidates": all_loras,
            })

        order = {"available": 0, "no-pattern": 1, "missing": 2}
        ecosystems.sort(key=lambda e: (order.get(e["status"], 9), e["label"]))

        return {
            "ecosystems": ecosystems,
            "platformLinks": PLATFORM_LINKS,
        }

    # ------------------------------------------------------------
    # 辅助
    # ------------------------------------------------------------
    def _find_family(self, arch: str) -> str:
        for fid, family in ARCH_FAMILIES.items():
            if arch in family["members"]:
                return fid
        return arch

    def _family_label(self, family_id: str, architectures: dict) -> str:
        if family_id in ARCH_FAMILIES:
            return ARCH_FAMILIES[family_id]["label"]
        arch_def = architectures.get(family_id, {})
        return arch_def.get("label", family_id)

    def _brief(self, m: dict) -> dict:
        return {
            "file": m.get("file"),
            "dir": m.get("dir"),
            "arch": m.get("arch"),
            "role": m.get("role"),
            "defaultWeight": m.get("defaultWeight"),
            "triggerWord": m.get("triggerWord"),
        }