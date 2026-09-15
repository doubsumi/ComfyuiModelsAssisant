"""HTTP 路由分发"""
import json
import urllib.parse
from http.server import BaseHTTPRequestHandler
from pathlib import Path


class AppContext:
    def __init__(self):
        self.config = None
        self.scanner = None
        self.cache_store = None
        self.registry_store = None
        self.notes_store = None


class Router:
    def __init__(self):
        self.routes: list[tuple[str, str, callable]] = []
        self.static_dirs: dict[str, Path] = {}
        self.default_page: Path | None = None

    def add(self, method: str, path: str, handler):
        self.routes.append((method.upper(), path, handler))

    def mount_static(self, url_prefix: str, directory: Path):
        self.static_dirs[url_prefix.rstrip("/")] = Path(directory).resolve()

    def dispatch(self, method: str, path: str, query: dict, body, ctx: AppContext):
        for m, p, h in self.routes:
            if m == method and p == path:
                try:
                    return h(ctx, query, body)
                except Exception as e:
                    import traceback
                    traceback.print_exc()
                    return 500, {"ok": False, "error": f"{type(e).__name__}: {e}"}

        if method == "GET":
            if path in ("/", "/index.html") and self.default_page:
                if self.default_page.is_file():
                    return self._serve_file(self.default_page)
            for prefix, directory in self.static_dirs.items():
                if path.startswith(prefix + "/"):
                    rel = path[len(prefix) + 1:]
                    target = (directory / rel).resolve()
                    if not str(target).startswith(str(directory)):
                        continue
                    if target.is_file():
                        return self._serve_file(target)
        
        if method == "PUT":
            for m, p, h in self.routes:
                if m == "PUT" and p == path:
                    try:
                        return h(ctx, query, body)
                    except Exception as e:
                        import traceback
                        traceback.print_exc()
                        return 500, {"ok": False, "error": f"{type(e).__name__}: {e}"}

        if method == "DELETE":
            for m, p, h in self.routes:
                if m == "DELETE" and p == path:
                    try:
                        return h(ctx, query, body)
                    except Exception as e:
                        import traceback
                        traceback.print_exc()
                        return 500, {"ok": False, "error": f"{type(e).__name__}: {e}"}

        return 404, {"ok": False, "error": "Not Found"}

    @staticmethod
    def _serve_file(path: Path):
        ctype = {
            ".html": "text/html; charset=utf-8",
            ".css": "text/css; charset=utf-8",
            ".js": "application/javascript; charset=utf-8",
            ".json": "application/json; charset=utf-8",
            ".svg": "image/svg+xml",
            ".png": "image/png",
            ".ico": "image/x-icon",
        }.get(path.suffix.lower(), "application/octet-stream")
        return 200, path.read_bytes(), ctype


class HTTPHandler(BaseHTTPRequestHandler):
    router: Router = None
    ctx: AppContext = None

    def log_message(self, fmt, *args):
        if args and str(args[0]).startswith(("4", "5")):
            super().log_message(fmt, *args)

    def _parse_body(self):
        length = int(self.headers.get("Content-Length", 0))
        if not length:
            return None
        raw = self.rfile.read(length)
        try:
            return json.loads(raw.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            return None

    def _respond(self, result):
        if len(result) == 3:
            status, body, ctype = result
        else:
            status, payload = result
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            ctype = "application/json; charset=utf-8"

        if isinstance(body, str):
            body = body.encode("utf-8")
        elif not isinstance(body, (bytes, bytearray)):
            body = json.dumps(body, ensure_ascii=False).encode("utf-8")

        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        query = urllib.parse.parse_qs(parsed.query)
        self._respond(self.router.dispatch("GET", parsed.path, query, None, self.ctx))

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        query = urllib.parse.parse_qs(parsed.query)
        body = self._parse_body()
        self._respond(self.router.dispatch("POST", parsed.path, query, body, self.ctx))

    def do_PUT(self):
        parsed = urllib.parse.urlparse(self.path)
        query = urllib.parse.parse_qs(parsed.query)
        body = self._parse_body()
        self._respond(self.router.dispatch("PUT", parsed.path, query, body, self.ctx))

    def do_DELETE(self):
        parsed = urllib.parse.urlparse(self.path)
        query = urllib.parse.parse_qs(parsed.query)
        body = self._parse_body()
        self._respond(self.router.dispatch("DELETE", parsed.path, query, body, self.ctx))