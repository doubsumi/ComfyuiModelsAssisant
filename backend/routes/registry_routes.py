"""注册表 API"""
import json
from pathlib import Path


def register(router):
    router.add("GET",  "/api/registry",               handle_get_registry)
    router.add("GET",  "/api/registry/scan",          handle_registry_scan)
    router.add("GET",  "/api/registry/update-prompt", handle_update_prompt)
    router.add("POST", "/api/registry/patch",         handle_patch)
    router.add("GET",  "/api/registry/history",       handle_history)
    router.add("POST", "/api/registry/rollback",      handle_rollback)


def _get_registry(ctx):
    """惰性创建 ModelRegistry（依赖 data 目录路径）"""
    if not hasattr(ctx, "_registry") or ctx._registry is None:
        from backend.services.model_registry import ModelRegistry
        data_dir = ctx.config.store.path.parent
        ctx._registry = ModelRegistry(
            registry_store=ctx.registry_store,
            architectures_path=data_dir / "architectures.json",
            patches_dir=data_dir / "patches",
        )
    return ctx._registry


def _do_scan(ctx, force: bool = False) -> list[dict] | None:
    models_dir = ctx.config.get("modelsDir")
    if not models_dir or not Path(models_dir).is_dir():
        return None

    threshold = ctx.config.get("confidenceThreshold", 0.6)
    ctx.scanner.confidence_threshold = threshold
    entries = [e.to_dict() for e in ctx.scanner.scan_directory(models_dir, threshold)]

    # 与注册表合并：注册表的已确证字段覆盖扫描推断结果
    registry = _get_registry(ctx)
    registry_models = {
        (m["file"], m["dir"]): m
        for m in registry.store.load().get("models", [])
    }

    merged: list[dict] = []
    for e in entries:
        key = (e["file"], e["dir"])
        reg = registry_models.get(key)
        if reg:
            # 注册表字段优先；保留扫描的实时字段
            combined = {**e, **reg}
            combined["sizeBytes"] = e.get("sizeBytes", reg.get("sizeBytes"))
            combined["mtime"] = e.get("mtime", reg.get("mtime"))
            merged.append(combined)
        else:
            merged.append(e)
    return merged


# ------------------------------------------------------------
# GET
# ------------------------------------------------------------
def handle_get_registry(ctx, query, body):
    registry = _get_registry(ctx)
    return 200, registry.load()


def handle_registry_scan(ctx, query, body):
    force = (query.get("force", ["0"])[0] == "1")
    entries = _do_scan(ctx, force=force)
    if entries is None:
        return 400, {"ok": False, "error": "模型目录未配置或不存在"}

    registry = _get_registry(ctx)
    known = {(m["file"], m["dir"]) for m in registry.store.load().get("models", [])}

    unregistered = [e for e in entries if (e["file"], e["dir"]) not in known]
    needs_llm = [e for e in entries if e.get("needsLlm")]
    # 待补全也包含已在册但 needsLlm 的条目
    incomplete_registered = [
        e for e in entries
        if (e["file"], e["dir"]) in known and e.get("needsLlm")
    ]

    return 200, {
        "ok": True,
        "scannedCount": len(entries),
        "registeredCount": len(known),
        "unregisteredCount": len(unregistered),
        "needsLlmCount": len(incomplete_registered),
        "pendingCount": len(unregistered) + len(incomplete_registered),
        "models": entries,
    }


def handle_update_prompt(ctx, query, body):
    entries = _do_scan(ctx)
    if entries is None:
        return 400, {"ok": False, "error": "模型目录未配置或不存在"}

    registry = _get_registry(ctx)
    prompt, count = registry.build_prompt(entries)

    if count == 0:
        return 200, {
            "ok": True,
            "targetCount": 0,
            "prompt": "",
            "message": "所有模型都已注册且无需补全",
        }

    return 200, {
        "ok": True,
        "targetCount": count,
        "prompt": prompt,
    }


def handle_history(ctx, query, body):
    registry = _get_registry(ctx)
    limit = int((query.get("limit", ["100"])[0]))
    items = registry.list_history(limit)
    return 200, {"ok": True, "items": items}


# ------------------------------------------------------------
# POST
# ------------------------------------------------------------
def handle_patch(ctx, query, body):
    if not isinstance(body, dict) or "patch" not in body:
        return 400, {"ok": False, "error": "请求体缺少 patch 字段"}

    entries = _do_scan(ctx)
    if entries is None:
        return 400, {"ok": False, "error": "模型目录未配置或不存在"}

    registry = _get_registry(ctx)
    result = registry.apply_patch(body["patch"], entries)

    if not result["ok"]:
        return 400, result

    # 按保留策略清理历史
    keep = ctx.config.get("patchHistoryRetention", 100)
    try:
        registry.prune_history(keep)
    except Exception:
        pass

    return 200, result


def handle_rollback(ctx, query, body):
    if not isinstance(body, dict) or "patchId" not in body:
        return 400, {"ok": False, "error": "缺少 patchId"}

    registry = _get_registry(ctx)
    result = registry.rollback(str(body["patchId"]))

    if not result["ok"]:
        return 400, result

    return 200, result