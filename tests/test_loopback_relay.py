"""The Safari-compatible relay exposes one game's assets, never engine controls."""
import importlib.util
import json
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from urllib.error import HTTPError
from urllib.request import ProxyHandler, Request, build_opener

import pytest

SPEC = importlib.util.spec_from_file_location("fright_feud_relay", Path(__file__).parents[1] / "desktop/relay.py")
relay = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(relay)


@pytest.fixture
def servers():
    requests = []

    class Engine(BaseHTTPRequestHandler):
        def do_GET(self):
            requests.append((self.command, self.path, self.headers.get("Host"), self.headers.get("Authorization")))
            if self.path.endswith("redirect"):
                self.send_response(302)
                self.send_header("Location", "https://example.com/")
                self.end_headers()
                return
            payload = b'{"name":"app-engine"}' if self.path == "/api/engine" else b"game asset"
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(payload)

        def do_HEAD(self):
            self.do_GET()

        def log_message(self, *args):
            pass

    engine = ThreadingHTTPServer(("127.0.0.1", 0), Engine)
    Thread(target=engine.serve_forever, daemon=True).start()
    proxy = relay.make_server(engine.server_port, 0, "test_nonce_12345678901234567890")
    Thread(target=proxy.serve_forever, daemon=True).start()
    yield engine, proxy, requests
    proxy.shutdown()
    proxy.server_close()
    engine.shutdown()
    engine.server_close()


def get(proxy, path, **headers):
    request = Request(f"http://127.0.0.1:{proxy.server_port}{path}", headers=headers)
    return build_opener(ProxyHandler({})).open(request, timeout=3)


def test_asset_is_forwarded_with_isolated_upstream_host(servers):
    engine, proxy, requests = servers
    with get(proxy, "/apps/fright-feud/fonts/fonts.css", Authorization="secret") as response:
        assert response.read() == b"game asset"
        assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert requests == [("GET", "/apps/fright-feud/fonts/fonts.css", f"fright-feud.localhost:{engine.server_port}", None)]


@pytest.mark.parametrize("path", ["/", "/api/engine", "/api/apps", "/api/app-engine/catalog/refresh",
                                     "/apps/other/index.html", "/apps/fright-feud/../secret",
                                     "/apps/fright-feud/%2e%2e/secret", "/apps/fright-feud/%252e%252e/secret",
                                     "/apps/fright-feud/index.html?unsafe=1"])
def test_engine_controls_and_path_escapes_are_denied(servers, path):
    _, proxy, requests = servers
    with pytest.raises(HTTPError) as result:
        get(proxy, path)
    assert result.value.code in {400, 403, 404}
    assert requests == []


def test_foreign_host_is_denied(servers):
    _, proxy, requests = servers
    with pytest.raises(HTTPError) as result:
        get(proxy, "/apps/fright-feud/", Host="evil.example")
    assert result.value.code == 403
    assert requests == []


def test_health_identifies_the_owned_relay(servers):
    engine, proxy, requests = servers
    with get(proxy, "/__fright_feud_health") as response:
        value = json.load(response)
    assert value["name"] == "fright-feud-relay"
    assert value["engine_port"] == engine.server_port
    assert value["nonce"] == "test_nonce_12345678901234567890"
    assert requests == []


def test_upstream_redirect_is_not_followed_or_exposed(servers):
    _, proxy, requests = servers
    with pytest.raises(HTTPError) as result:
        get(proxy, "/apps/fright-feud/redirect")
    assert result.value.code == 502
    assert len(requests) == 1


def test_head_keeps_asset_length_without_returning_body(servers):
    _, proxy, requests = servers
    request = Request(f"http://127.0.0.1:{proxy.server_port}/apps/fright-feud/index.html", method="HEAD")
    with build_opener(ProxyHandler({})).open(request, timeout=3) as response:
        assert response.read() == b""
        assert response.headers["Content-Length"] == "10"
    assert requests[0][0] == "HEAD"


def test_post_never_reaches_the_engine(servers):
    _, proxy, requests = servers
    request = Request(f"http://127.0.0.1:{proxy.server_port}/apps/fright-feud/", data=b"action=install")
    with pytest.raises(HTTPError) as result:
        build_opener(ProxyHandler({})).open(request, timeout=3)
    assert result.value.code == 501
    assert requests == []
