#!/usr/bin/env python3
"""Refresh the production board and serve the workspace on localhost."""

from __future__ import annotations

import argparse
import subprocess
import sys
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit


ROOT = Path(__file__).resolve().parents[1]


class LocalHandler(SimpleHTTPRequestHandler):
    """Serve project views without exposing hidden credentials or external symlinks."""
    def send_head(self):
        path = unquote(urlsplit(self.path).path)
        if path == "/":
            self.send_response(302)
            self.send_header("Location", "/queue/board.html")
            self.end_headers()
            return None
        parts = path.replace('\\', '/').split('/')
        denied = any((part.startswith(".") and part != ".agents") or ':' in part or part in {"node_modules", "__pycache__"} for part in parts)
        target = Path(self.translate_path(self.path)).resolve()
        if denied or not target.is_relative_to(ROOT.resolve()):
            self.send_error(404)
            return None
        return super().send_head()

    def end_headers(self):
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        super().end_headers()

    def list_directory(self, path):
        self.send_error(404, "Directory listing is disabled")
        return None


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8767, help="localhost port (default: 8767)")
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("port must be between 1 and 65535")

    for name in ("board.bundle.js", "board.bundle.css"):
        if not (ROOT / "queue" / name).is_file():
            parser.error("frontend bundle missing; run npm ci && npm run build in queue/board-ui")
    try:
        import yaml  # noqa: F401
    except ImportError:
        parser.error("PyYAML missing; install requirements.txt with this Python interpreter")

    handler = partial(LocalHandler, directory=str(ROOT))
    try:
        server = ThreadingHTTPServer(("127.0.0.1", args.port), handler)
    except OSError as error:
        parser.error(f"cannot listen on localhost:{args.port}: {error}; choose another --port")
    with server:
        result = subprocess.run([sys.executable, str(ROOT / "queue" / "build_board.py")], cwd=ROOT)
        if result.returncode:
            raise SystemExit(result.returncode)
        print(f"Workbench: http://127.0.0.1:{args.port}/queue/board.html", flush=True)
        print("Press Ctrl+C to stop. Refresh records with python3 queue/build_board.py.", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            print("\nWorkbench stopped.")


if __name__ == "__main__":
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    if hasattr(sys.stderr, 'reconfigure'):
        sys.stderr.reconfigure(encoding='utf-8')
    main()
