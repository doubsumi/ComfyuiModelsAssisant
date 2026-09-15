"""预设 + 提示词模板 API"""
from backend.services.prompt_template_store import PromptTemplateStore
from backend.storage.preset_store import PresetStore


def register(router):
    # 预设
    router.add("GET",    "/api/presets",             handle_list_presets)
    router.add("POST",   "/api/presets",             handle_create_preset)
    router.add("GET",    "/api/presets/detail",      handle_get_preset)
    router.add("PUT",    "/api/presets/detail",      handle_update_preset)
    router.add("DELETE", "/api/presets/detail",      handle_delete_preset)

    # 提示词模板
    router.add("GET",    "/api/prompts/templates",   handle_list_templates)
    router.add("POST",   "/api/prompts/templates",   handle_create_template)
    router.add("DELETE", "/api/prompts/templates",   handle_delete_template)


# ------------------------------------------------------------
# 依赖
# ------------------------------------------------------------
def _get_preset_store(ctx) -> PresetStore:
    if not hasattr(ctx, "_preset_store") or ctx._preset_store is None:
        data_dir = ctx.config.store.path.parent
        ctx._preset_store = PresetStore(data_dir / "presets.json")
    return ctx._preset_store


def _get_template_store(ctx) -> PromptTemplateStore:
    if not hasattr(ctx, "_template_store") or ctx._template_store is None:
        ctx._template_store = PromptTemplateStore(_get_preset_store(ctx))
    return ctx._template_store


# ------------------------------------------------------------
# 预设
# ------------------------------------------------------------
def handle_list_presets(ctx, query, body):
    store = _get_preset_store(ctx)
    return 200, {"ok": True, "presets": store.list_presets()}


def handle_create_preset(ctx, query, body):
    if not isinstance(body, dict):
        return 400, {"ok": False, "error": "请求体必须是 JSON"}
    store = _get_preset_store(ctx)
    preset = store.create_preset(body)
    return 200, {"ok": True, "preset": preset}


def handle_get_preset(ctx, query, body):
    pid = (query.get("id") or [""])[0]
    if not pid:
        return 400, {"ok": False, "error": "缺少 id"}
    store = _get_preset_store(ctx)
    preset = store.get_preset(pid)
    if preset is None:
        return 404, {"ok": False, "error": "预设不存在"}
    return 200, {"ok": True, "preset": preset}


def handle_update_preset(ctx, query, body):
    if not isinstance(body, dict):
        return 400, {"ok": False, "error": "请求体必须是 JSON"}
    pid = body.get("id")
    if not pid:
        return 400, {"ok": False, "error": "缺少 id"}
    store = _get_preset_store(ctx)
    preset = store.update_preset(pid, body)
    if preset is None:
        return 404, {"ok": False, "error": "预设不存在"}
    return 200, {"ok": True, "preset": preset}


def handle_delete_preset(ctx, query, body):
    pid = (query.get("id") or [""])[0]
    if not pid:
        return 400, {"ok": False, "error": "缺少 id"}
    store = _get_preset_store(ctx)
    if not store.delete_preset(pid):
        return 404, {"ok": False, "error": "预设不存在"}
    return 200, {"ok": True}


# ------------------------------------------------------------
# 提示词模板
# ------------------------------------------------------------
def handle_list_templates(ctx, query, body):
    ecosystem_id = (query.get("ecosystemId") or [None])[0]
    store = _get_template_store(ctx)
    return 200, {"ok": True, "templates": store.list_all(ecosystem_id)}


def handle_create_template(ctx, query, body):
    if not isinstance(body, dict):
        return 400, {"ok": False, "error": "请求体必须是 JSON"}
    store = _get_template_store(ctx)
    template = store.save_user_template(body)
    return 200, {"ok": True, "template": template}


def handle_delete_template(ctx, query, body):
    tid = (query.get("id") or [""])[0]
    if not tid:
        return 400, {"ok": False, "error": "缺少 id"}
    store = _get_template_store(ctx)
    if not store.delete_user_template(tid):
        return 404, {"ok": False, "error": "模板不存在或为内置模板"}
    return 200, {"ok": True}