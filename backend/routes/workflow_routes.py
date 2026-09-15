"""工作流相关 API"""
from pathlib import Path


def register(router):
    router.add("POST", "/api/compatibility/check", handle_compatibility_check)
    router.add("GET",  "/api/workflow/patterns",   handle_list_patterns)
    router.add("POST", "/api/workflow/preview",    handle_workflow_preview)
    router.add("POST", "/api/workflow/generate",   handle_workflow_generate)
    router.add("POST", "/api/workflow/save",       handle_workflow_save)
    router.add("GET",  "/api/ecosystems/recommend",   handle_recommend_ecosystems)


# ------------------------------------------------------------
# 共享依赖
# ------------------------------------------------------------
def _get_registry(ctx):
    from backend.routes.registry_routes import _get_registry as _r
    return _r(ctx)


def _get_compat_engine(ctx):
    if not hasattr(ctx, "_compat_engine") or ctx._compat_engine is None:
        from backend.services.compatibility_engine import CompatibilityEngine
        ctx._compat_engine = CompatibilityEngine(_get_registry(ctx))
    return ctx._compat_engine


def _get_pattern_store(ctx):
    if not hasattr(ctx, "_pattern_store") or ctx._pattern_store is None:
        from backend.storage.graph_pattern_store import GraphPatternStore
        data_dir = ctx.config.store.path.parent
        ctx._pattern_store = GraphPatternStore(data_dir / "graph_patterns")
    return ctx._pattern_store


def _get_generator(ctx):
    if not hasattr(ctx, "_workflow_generator") or ctx._workflow_generator is None:
        from backend.services.workflow_generator import WorkflowGenerator
        ctx._workflow_generator = WorkflowGenerator(
            compat_engine=_get_compat_engine(ctx),
            pattern_store=_get_pattern_store(ctx),
        )
    return ctx._workflow_generator


def _do_scan(ctx):
    from backend.routes.registry_routes import _do_scan as _s
    return _s(ctx)


# ------------------------------------------------------------
# 兼容性检查
# ------------------------------------------------------------
def handle_compatibility_check(ctx, query, body):
    if not isinstance(body, dict):
        return 400, {"ok": False, "error": "请求体必须是 JSON"}

    selected = body.get("selectedFiles")
    if not isinstance(selected, list):
        return 400, {"ok": False, "error": "缺少 selectedFiles 数组"}

    scanned = _do_scan(ctx)
    if scanned is None:
        return 400, {"ok": False, "error": "模型目录未配置或不存在"}

    engine = _get_compat_engine(ctx)
    result = engine.check(selected, scanned)
    return 200, result


# ------------------------------------------------------------
# 图谱列表
# ------------------------------------------------------------
def handle_list_patterns(ctx, query, body):
    store = _get_pattern_store(ctx)
    return 200, {"ok": True, "patterns": store.list()}


# ------------------------------------------------------------
# 预览 / 生成
# ------------------------------------------------------------
def handle_workflow_preview(ctx, query, body):
    return _generate_impl(ctx, body, save=False)


def handle_workflow_generate(ctx, query, body):
    return _generate_impl(ctx, body, save=True)


def _generate_impl(ctx, body, save: bool):
    if not isinstance(body, dict):
        return 400, {"ok": False, "error": "请求体必须是 JSON"}

    scanned = _do_scan(ctx)
    if scanned is None:
        return 400, {"ok": False, "error": "模型目录未配置或不存在"}

    generator = _get_generator(ctx)
    result = generator.generate(body, scanned)

    if not result.get("ok"):
        return 400, result

    return 200, result


def handle_workflow_save(ctx, query, body):
    if not isinstance(body, dict):
        return 400, {"ok": False, "error": "请求体必须是 JSON"}

    workflow = body.get("workflow")
    name = (body.get("name") or "").strip()

    if not isinstance(workflow, dict):
        return 400, {"ok": False, "error": "缺少 workflow 对象"}
    if not name:
        return 400, {"ok": False, "error": "缺少 name"}

    # 文件名清洗（防止路径穿越）
    safe = "".join(c for c in name if c not in r'\/:*?"<>|').strip()
    if not safe:
        return 400, {"ok": False, "error": "文件名不合法"}
    if not safe.lower().endswith(".json"):
        safe += ".json"

    comfyui_root = ctx.config.get("comfyuiRoot")
    if not comfyui_root or not Path(comfyui_root).is_dir():
        return 400, {"ok": False, "error": f"ComfyUI 根目录不存在: {comfyui_root}"}

    target_dir = Path(comfyui_root) / "user" / "default" / "workflows"
    try:
        target_dir.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        return 500, {"ok": False, "error": f"无法创建目录: {e}"}

    target = target_dir / safe
    try:
        import json
        target.write_text(
            json.dumps(workflow, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except OSError as e:
        return 500, {"ok": False, "error": f"写入失败: {e}"}

    return 200, {"ok": True, "savedPath": str(target), "fileName": safe}


def handle_recommend_ecosystems(ctx, query, body):
    scanned = _do_scan(ctx)
    if scanned is None:
        return 400, {"ok": False, "error": "模型目录未配置或不存在"}

    from backend.services.ecosystem_recommender import EcosystemRecommender
    recommender = EcosystemRecommender(_get_registry(ctx), _get_pattern_store(ctx))
    result = recommender.recommend(scanned)
    return 200, {"ok": True, **result}