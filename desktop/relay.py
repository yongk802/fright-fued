#!/usr/bin/env python3
"""Serve one engine-hosted game on numeric loopback for older Safari.

This is an app-scoped transport adapter, not an engine/admin API proxy. Its
separate port maintains browser origin isolation without DNS or host-file edits.
"""
import argparse
from http.client import HTTPConnection, HTTPException
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import tempfile
from threading import Thread
import time
from urllib.parse import unquote, urlsplit

PREFIX = "/apps/fright-feud/"
MAX_ASSET_BYTES = 16 * 1024 * 1024


class RelayServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, engine_port, listen_port, nonce):
        self.engine_port = engine_port
        self.nonce = nonce
        super().__init__(("127.0.0.1", listen_port), RelayHandler)


class RelayHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.0"

    def log_message(self, *args):
        pass

    def do_GET(self):
        self.serve_asset()

    def do_HEAD(self):
        self.serve_asset(head=True)

    def serve_asset(self, head=False):
        expected_host = f"127.0.0.1:{self.server.server_port}"
        if self.headers.get("Host") != expected_host:
            self.send_error(403, "Numeric loopback host required")
            return
        parsed = urlsplit(self.path)
        if parsed.scheme or parsed.netloc or parsed.query or parsed.fragment:
            self.send_error(400, "Only local asset paths are accepted")
            return
        if parsed.path == "/__fright_feud_health":
            payload = json.dumps({"name": "fright-feud-relay", "engine_port": self.server.engine_port,
                                  "nonce": self.server.nonce}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            if not head:
                self.wfile.write(payload)
            return
        # Reject encoded escapes as well as literal traversal. No engine control
        # path is reachable, even when the browser supplies an absolute request.
        decoded = unquote(parsed.path)
        if (not decoded.startswith(PREFIX) or "%" in decoded
                or ".." in decoded.split("/") or "\\" in decoded
                or any(ord(char) < 32 for char in decoded)):
            self.send_error(404, "Only Fright Feud assets are served")
            return
        connection = HTTPConnection("127.0.0.1", self.server.engine_port, timeout=8)
        try:
            connection.request("HEAD" if head else "GET", parsed.path, headers={
                "Host": f"fright-feud.localhost:{self.server.engine_port}",
                "Accept-Encoding": "identity",
            })
            response = connection.getresponse()
            if 300 <= response.status < 400:
                raise ValueError("Engine redirects are not relayed")
            declared = response.getheader("Content-Length")
            if declared is not None and int(declared) > MAX_ASSET_BYTES:
                raise ValueError("Engine asset exceeds the relay limit")
            body = b"" if head else response.read(MAX_ASSET_BYTES + 1)
            if len(body) > MAX_ASSET_BYTES:
                raise ValueError("Engine asset exceeds the relay limit")
            self.send_response(response.status)
            for key in ("Content-Type", "Content-Language", "Content-Security-Policy", "Cache-Control", "ETag", "Last-Modified"):
                value = response.getheader(key)
                if value is not None:
                    self.send_header(key, value)
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Content-Length", declared if head and declared is not None else str(len(body)))
            self.end_headers()
            if not head:
                self.wfile.write(body)
        except (OSError, ValueError, HTTPException):
            self.send_error(502, "The local App Engine is unavailable")
        finally:
            connection.close()


def make_server(engine_port, listen_port=0, nonce=""):
    if not 1024 <= engine_port <= 65535 or not (listen_port == 0 or 1024 <= listen_port <= 65535):
        raise ValueError("Invalid local port")
    if not re.fullmatch(r"[A-Za-z0-9_-]{20,128}", nonce):
        raise ValueError("Invalid relay nonce")
    return RelayServer(engine_port, listen_port, nonce)


def watch_engine(server):
    failures = 0
    while failures < 3:
        time.sleep(3)
        connection = HTTPConnection("127.0.0.1", server.engine_port, timeout=2)
        try:
            connection.request("GET", "/api/engine")
            response = connection.getresponse()
            value = json.loads(response.read(65536))
            failures = 0 if response.status == 200 and value.get("name") == "app-engine" else failures + 1
        except (OSError, ValueError, AttributeError, HTTPException):
            failures += 1
        finally:
            connection.close()
    server.shutdown()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--engine-port", type=int, required=True)
    parser.add_argument("--listen-port", type=int, default=0)
    parser.add_argument("--state-file", type=Path, required=True)
    parser.add_argument("--nonce", required=True)
    args = parser.parse_args()
    server = make_server(args.engine_port, args.listen_port, args.nonce)
    args.state_file.parent.mkdir(parents=True, exist_ok=True)
    fd, path = tempfile.mkstemp(prefix=".relay-", dir=args.state_file.parent)
    try:
        with os.fdopen(fd, "w") as target:
            json.dump({"pid": os.getpid(), "port": server.server_port,
                       "engine_port": args.engine_port, "nonce": args.nonce}, target)
        os.replace(path, args.state_file)
        Thread(target=watch_engine, args=(server,), daemon=True).start()
        server.serve_forever(poll_interval=.2)
    finally:
        server.server_close()
        if os.path.exists(path):
            os.unlink(path)


if __name__ == "__main__":
    main()
