"""
工作流生成器门面
================
串起 compat check + graph build + serialize + validate。
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from backend.services.compatibility_engine import CompatibilityEngine
from backend.services.graph_builder import GraphBuilder, BuildError
from backend.services.workflow_serializer import WorkflowSerializer
from backend.storage.graph_pattern_store import GraphPatternStore


class WorkflowGenerator:
    def __init__(
        self,
        compat_engine: CompatibilityEngine,
        pattern_store: GraphPatternStore,
    ):
        self.compat = compat_engine
        self.pattern_store = pattern_store
        self.builder = GraphBuilder()
        self.serializer = WorkflowSerializer()

    # ------------------------------------------------------------
    # 生成
    # ------------------------------------------------------------
    def generate(self, request: dict, scanned: list[dict]) -> dict:
        """核心入口。返回 { ok, workflow?, errors?, warnings?, pluginDependencies? }"""
        ecosystem_id = request.get("ecosystemId")
        if not ecosystem_id:
            return self._fail("缺少 ecosystemId")

        pattern = self.pattern_store.get(ecosystem_id)
        if pattern is None:
            return self._fail(f"找不到图谱: {ecosystem_id}")

        # 1. 兼容性二次校验
        selected = self._selected_from_request(request)
        compat = self.compat.check(selected, scanned)
        if not compat.get("ok"):
            return {
                "ok": False,
                "errors": self._compat_errors(compat),
                "compatibility": compat,
            }

        # 2. 校验请求的 arch 与 pattern 的兼容架构匹配
        primary = compat.get("primaryUnet")
        if primary:
            arch = primary.get("arch")
            if arch and arch not in pattern.get("compatibleArchitectures", []):
                return self._fail(
                    f"主模型架构 {arch} 不在图谱 {ecosystem_id} 支持范围内",
                    compatibility=compat,
                )

        # 3. 构建
        try:
            build_result = self.builder.build(pattern, request)
        except BuildError as e:
            return self._fail(f"图构建失败: {e}")
        except Exception as e:
            return self._fail(f"内部错误: {type(e).__name__}: {e}")

        # 4. 序列化
        workflow = self.serializer.serialize(build_result)

        # 5. 自检
        validation = self.serializer.validate(workflow)

        # 6. 插件依赖
        plugins = pattern.get("pluginDependencies", [])

        return {
            "ok": validation["ok"],
            "workflow": workflow,
            "pluginDependencies": plugins,
            "validationWarnings": validation.get("warnings", []),
            "errors": validation.get("errors", []),
            "compatibility": {
                "ok": compat.get("ok"),
                "resolved": compat.get("resolved"),
            },
        }

    # ------------------------------------------------------------
    # 辅助
    # ------------------------------------------------------------
    def _selected_from_request(self, request: dict) -> list[dict]:
        """把 request.models + request.loras 转成兼容性引擎需要的 selectedFiles 列表。"""
        out = []
        for role, file_name in (request.get("models") or {}).items():
            if not file_name:
                continue
            # 需要找到 dir：从 request.models 里我们无法直接知道 dir，但 request 里可以显式带 fileDirs
            dir_ = (request.get("modelDirs") or {}).get(role, self._infer_dir(role))
            out.append({"file": file_name, "dir": dir_})
        for lora in (request.get("loras") or []):
            out.append({"file": lora["file"], "dir": "loras"})
        return out

    def _infer_dir(self, role: str) -> str:
        return {
            "unet": "diffusion_models",
            "encoder": "text_encoders",
            "vae": "vae",
            "videoVae": "vae",
            "audioVae": "vae",
            "lora": "loras",
            "checkpoint": "checkpoints",
        }.get(role, "diffusion_models")

    def _compat_errors(self, compat: dict) -> list[str]:
        errs = []
        if compat.get("error"):
            errs.append(compat["error"])
        if compat.get("needChoice"):
            errs.append(compat["needChoice"]["reason"])
        for m in compat.get("missing", []):
            errs.append(f"缺失 {m['role']}: {m['reason']}")
        for c in compat.get("conflicts", []):
            if c.get("severity") == "error":
                errs.append(c["message"])
        for e in compat.get("excluded", []):
            errs.append(f"已排除 {e['file']}: {e.get('reason', '不兼容')}")
        return errs

    def _fail(self, msg: str, **extra) -> dict:
        return {
            "ok": False,
            "errors": [msg],
            **extra,
        }