"""旧有 API：scan / config / notes / open"""
import os
from pathlib import Path


FILE_EXTS = {".safetensors", ".ckpt", ".pt", ".pth", ".bin", ".gguf", ".sft", ".onnx"}


def register(router):
    router.add("GET",  "/api/scan",        handle_scan)
    router.add("GET",  "/api/config",      handle_get_config)
    router.add("POST", "/api/config",      handle_post_config)
    router.add("GET",  "/api/notes",       handle_get_notes)
    router.add("POST", "/api/notes",       handle_post_notes)
    router.add("POST", "/api/notes/clear", handle_clear_notes)
    router.add("GET",  "/api/open",        handle_open_folder)


def _walk(models_dir: str) -> list[dict]:
    root = Path(models_dir)
    out = []
    for p in root.rglob("*"):
        if not p.is_file():
            continue
        if p.suffix.lower() not in FILE_EXTS:
            continue
        rel = p.relative_to(root)
        if len(rel.parts) < 2:
            continue
        out.append({
            "dir": rel.parts[0],
            "name": p.name,
            "relPath": str(rel).replace("\\", "/"),
            "sizeBytes": p.stat().st_size,
        })
    out.sort(key=lambda x: (x["dir"], x["name"]))
    return out


def handle_scan(ctx, query, body):
    models_dir = ctx.config.get("modelsDir")
    if not models_dir or not Path(models_dir).is_dir():
        return 400, {"ok": False, "error": "模型目录不存在", "modelsDir": models_dir}

    force = (query.get("force", ["0"])[0] == "1")
    cached = None if force else ctx.cache_store.get(models_dir, ctx.config.get("scanCacheMaxAge", 300))
    if cached is None:
        cached = _walk(models_dir)
        ctx.cache_store.set(models_dir, cached)

    return 200, {"ok": True, "modelsDir": models_dir, "files": cached, "count": len(cached)}


def handle_get_config(ctx, query, body):
    return 200, ctx.config.data


def handle_post_config(ctx, query, body):
    if not isinstance(body, dict):
        return 400, {"ok": False, "error": "请求体必须是 JSON"}
    new_dir = str(body.get("modelsDir", "")).strip()
    if new_dir and not Path(new_dir).is_dir():
        return 400, {"ok": False, "error": f"目录不存在: {new_dir}"}
    try:
        ctx.config.update(body)
        ctx.cache_store.invalidate()
    except ValueError as e:
        return 400, {"ok": False, "error": str(e)}
    return 200, {"ok": True, **ctx.config.data}


def handle_get_notes(ctx, query, body):
    return 200, ctx.notes_store.load()


def handle_post_notes(ctx, query, body):
    if not isinstance(body, dict) or "key" not in body:
        return 400, {"ok": False, "error": "缺少 key"}
    key = str(body["key"])
    value = str(body.get("value", ""))
    notes = ctx.notes_store.load()
    if value:
        notes[key] = value
    else:
        notes.pop(key, None)
    ctx.notes_store.save(notes)
    return 200, {"ok": True}


def handle_clear_notes(ctx, query, body):
    ctx.notes_store.save({})
    return 200, {"ok": True}


def handle_open_folder(ctx, query, body):
    rel_dir = (query.get("dir") or [""])[0]
    if not rel_dir:
        return 400, {"ok": False, "error": "缺少 dir 参数"}
    if ".." in rel_dir or rel_dir.startswith(("/", "\\")):
        return 400, {"ok": False, "error": "非法路径"}
    models_dir = ctx.config.get("modelsDir")
    target = Path(models_dir) / rel_dir
    if not target.is_dir():
        return 404, {"ok": False, "error": f"目录不存在: {target}"}
    try:
        os.startfile(str(target))
        return 200, {"ok": True, "path": str(target)}
    except Exception as e:
        return 500, {"ok": False, "error": str(e)}