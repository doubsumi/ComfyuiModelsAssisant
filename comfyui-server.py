#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ComfyUI 模型管理器 · 入口
==========================
- 启动 HTTP 服务
- 自动打开浏览器
- 零第三方依赖
"""
import socket
import sys
import threading
import webbrowser
from http.server import ThreadingHTTPServer
from pathlib import Path

BASE_DIR = Path(__file__).parent.resolve()
sys.path.insert(0, str(BASE_DIR))

from backend.config import Config
from backend.routes.base import AppContext, HTTPHandler, Router
from backend.routes import model_routes, registry_routes
from backend.services.model_scanner import ModelScanner
from backend.storage.cache_store import ScanCacheStore
from backend.storage.json_store import JSONStore
from backend.storage.registry_store import RegistryStore
from backend.routes import model_routes, registry_routes, workflow_routes, preset_routes


def find_free_port(start: int, host: str, tries: int = 50) -> int | None:
    for p in range(start, start + tries):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                s.bind((host, p))
                return p
            except OSError:
                continue
    return None


def build_context() -> AppContext:
    data_dir = BASE_DIR / "data"
    data_dir.mkdir(exist_ok=True)

    ctx = AppContext()
    ctx.config = Config(data_dir)
    ctx.scanner = ModelScanner()
    ctx.cache_store = ScanCacheStore(data_dir / "scan_cache.json")
    ctx.registry_store = RegistryStore(data_dir / "model_registry.json")
    ctx.notes_store = JSONStore(data_dir / "notes.json", default_factory=dict)

    # 保证内置 architectures.json 存在
    arch_path = data_dir / "architectures.json"
    if not arch_path.exists():
        from backend.services.builtin_architectures import ARCHITECTURES_CONTENT
        arch_path.write_text(ARCHITECTURES_CONTENT, encoding="utf-8")

    return ctx


def build_router() -> Router:
    router = Router()
    model_routes.register(router)
    registry_routes.register(router)
    workflow_routes.register(router)
    preset_routes.register(router)
    router.mount_static("/static", BASE_DIR / "frontend")
    router.default_page = BASE_DIR / "frontend" / "index.html"
    return router


def main():
    ctx = build_context()
    router = build_router()
    HTTPHandler.router = router
    HTTPHandler.ctx = ctx

    host = "127.0.0.1"
    port = find_free_port(ctx.config.get("port", 17890), host)
    if port is None:
        print("找不到可用端口")
        input("按回车退出...")
        sys.exit(1)

    server = ThreadingHTTPServer((host, port), HTTPHandler)
    url = f"http://{host}:{port}/"

    print("=" * 60)
    print("  🧠 ComfyUI 模型管理器")
    print("=" * 60)
    print(f"  地址     : {url}")
    print(f"  模型目录 : {ctx.config.get('modelsDir')}")
    print(f"  数据目录 : {BASE_DIR / 'data'}")
    print()
    print("  关闭此窗口或按 Ctrl+C 退出")
    print("=" * 60)

    threading.Timer(0.5, lambda: webbrowser.open(url)).start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n正在停止...")
    finally:
        server.shutdown()
        server.server_close()


if __name__ == "__main__":
    main()