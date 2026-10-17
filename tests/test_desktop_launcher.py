"""Launcher behavior through real local HTTP and child processes; no engine deps."""
from concurrent.futures import ThreadPoolExecutor
import importlib.util
import json
from pathlib import Path
import platform
import plistlib
import shutil
import socket
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

REPO = Path(__file__).resolve().parents[1]


def launcher():
    path = REPO / "desktop/launcher.py"
    assert path.is_file(), "The desktop launcher coordinator must exist"
    spec = importlib.util.spec_from_file_location("fright_launcher", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


FAKE_ENGINE = r'''
import json, os
from pathlib import Path
from http.server import BaseHTTPRequestHandler, HTTPServer
apps = Path(os.environ["APP_ENGINE_APPS_DIR"])
class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args): pass
    def do_GET(self):
        if self.path == "/api/engine": data = {"name": "app-engine"}
        elif self.path == "/api/apps":
            data = [{"id": "fright-feud", "url": "http://fright-feud.localhost:%s/apps/fright-feud/#atrium_state_token=local" % self.server.server_port}] if (apps / "fright-feud/app.json").is_file() else []
        elif self.path == "/api/app-engine/studio/roots": data = [{"root": str(apps), "inspect": True, "create": True, "write": True}]
        elif self.path == "/environment": data = {k:v for k,v in os.environ.items() if k.startswith("APP_ENGINE_")}
        elif self.path.startswith('/apps/fright-feud/'):
            relative = self.path[len('/apps/fright-feud/'):] or 'index.html'
            path = apps / 'fright-feud' / relative
            if not path.is_file(): self.send_error(404); return
            payload = path.read_bytes()
            self.send_response(200); self.send_header('Content-Type', 'text/javascript' if path.suffix == '.js' else 'text/html'); self.end_headers(); self.wfile.write(payload); return
        else: self.send_error(404); return
        payload = json.dumps(data).encode()
        self.send_response(200); self.send_header("Content-Length", str(len(payload))); self.end_headers(); self.wfile.write(payload)
    def do_POST(self):
        self.rfile.read(int(self.headers.get("Content-Length", 0)))
        self.send_response(200); self.end_headers(); self.wfile.write(b"{}")
HTTPServer((os.environ["APP_ENGINE_HOST"], int(os.environ["APP_ENGINE_PORT"])), Handler).serve_forever()
'''


FAKE_RELAY = r'''
import argparse, json, os
from pathlib import Path
from http.server import BaseHTTPRequestHandler, HTTPServer
p = argparse.ArgumentParser()
p.add_argument("--engine-port", type=int)
p.add_argument("--listen-port", type=int)
p.add_argument("--state-file", type=Path)
p.add_argument("--nonce")
args = p.parse_args()
class Handler(BaseHTTPRequestHandler):
    def log_message(self, *values): pass
    def do_GET(self):
        if self.path != "/__fright_feud_health": self.send_error(404); return
        payload = json.dumps({"name":"fright-feud-relay", "engine_port":args.engine_port, "nonce":args.nonce}).encode()
        self.send_response(200); self.send_header("Content-Length", str(len(payload))); self.end_headers(); self.wfile.write(payload)
server = HTTPServer(("127.0.0.1", args.listen_port), Handler)
state = {"pid":os.getpid(), "port":server.server_port, "engine_port":args.engine_port, "nonce":args.nonce, "home":os.environ["HOME"]}
stage = args.state_file.with_suffix(".temporary")
stage.write_text(json.dumps(state))
os.replace(stage, args.state_file)
server.serve_forever()
'''


@pytest.fixture
def bundle(tmp_path):
    app = tmp_path / "Downloaded Folder With Spaces/Fright Feud.app"
    resources = app / "Contents/Resources"
    (app / "Contents").mkdir(parents=True)
    (app / "Contents/Info.plist").write_bytes(plistlib.dumps({"CFBundleIdentifier": "com.yongk802.fright-feud", "CFBundleExecutable": "FrightFeud"}))
    (app / "Contents/MacOS").mkdir()
    (app / "Contents/MacOS/FrightFeud").write_text("native executable placeholder")
    (app / "Contents/MacOS/FrightFeud").chmod(0o755)
    (resources / "engine").mkdir(parents=True)
    (resources / "engine/engine.py").write_text(FAKE_ENGINE)
    (resources / "relay.py").write_text(FAKE_RELAY)
    (resources / "game/fonts").mkdir(parents=True)
    (resources / "game/app.json").write_text(json.dumps({"id": "fright-feud"}))
    (resources / "game/index.html").write_text("bundled game")
    (resources / "game/fonts/OFL.txt").write_text("font license")
    (resources / "bundle.json").write_text(json.dumps({"version": "1.1.0", "game_id": "fright-feud", "engine_commit": "a" * 40}))
    arch = "arm64" if platform.machine() == "arm64" else "x86_64"
    runtime = resources / "runtimes" / arch / "python/bin"
    runtime.mkdir(parents=True)
    (runtime / "python3.12").symlink_to(sys.executable)
    home = tmp_path / "User Home With Spaces"
    home.mkdir()
    return app, resources, home


@pytest.fixture
def started_engines():
    pids = []
    yield pids
    # Test-owned processes only; production must never kill a service.
    import os
    import signal
    for pid in set(pids):
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            pass


def free_port():
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return listener.getsockname()[1]


def run_launch(module, bundle, pids, **kwargs):
    app, resources, home = bundle
    result = module.launch(resources, home, kwargs.pop("preferred_port", free_port()), bundle=app, **kwargs)
    for key in ("pid", "relay_pid"):
        if result.get(key):
            pids.append(result[key])
    return result


class ExistingEngine:
    def __init__(self, root, *, game=True, name="app-engine", url=None, roots=None, delays=None):
        self.game = game
        self.name = name
        self.url = url
        self.refreshes = 0
        self.root = root
        self.roots = roots
        self.delays = delays or {}
        owner = self
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args): pass
            def do_GET(self):
                time.sleep(owner.delays.get(self.path, 0))
                if self.path == "/api/engine": data = {"name": owner.name}
                elif self.path == "/api/apps": data = ([{"id": "fright-feud", "url": owner.url or f"http://fright-feud.localhost:{self.server.server_port}/apps/fright-feud/#atrium_state_token=existing"}] if owner.game else [])
                elif self.path == "/api/app-engine/studio/roots": data = owner.roots if owner.roots is not None else [{"root": str(root), "inspect": True, "create": True, "write": True}]
                else: self.send_error(404); return
                body = json.dumps(data).encode()
                self.send_response(200); self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)
            def do_POST(self):
                time.sleep(owner.delays.get(self.path, 0))
                self.rfile.read(int(self.headers.get("Content-Length", 0)))
                if self.path != "/api/app-engine/catalog/refresh": self.send_error(404); return
                owner.refreshes += 1
                owner.game = (root / "fright-feud/app.json").exists()
                self.send_response(200); self.end_headers(); self.wfile.write(b"{}")
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.port = self.server.server_port
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
    def __enter__(self): return self
    def __exit__(self, *args):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()


def test_fresh_launch_installs_durable_resources_and_reuses_engine(bundle, started_engines):
    module = launcher()
    app, resources, home = bundle
    first = run_launch(module, bundle, started_engines)
    assert first["reused_engine"] is False
    assert first["installed_game"] is True
    assert first["pid"] > 0
    assert first["url"].startswith("http://127.0.0.1:")
    assert first["relay_pid"] > 0
    assert first["engine_port"] > 0
    installed = home / "Applications/Fright Feud.app/Contents/Resources"
    assert (installed / "game/fonts/OFL.txt").read_text() == "font license"
    shutil.rmtree(app.parent)
    second = module.launch(installed, home, 8770, install_bundle=False)
    assert second["reused_engine"] is True
    assert second["installed_game"] is False
    assert second["url"] == first["url"]
    assert second["pid"] == first["pid"]
    assert second["relay_pid"] == first["relay_pid"]
    assert len(list((home / "Library/Application Support/Fright Feud").glob("releases/*/engine/engine.py"))) == 1


def test_phone_capable_bundle_opens_paired_board_and_reuses_service(bundle, started_engines):
    import runpy
    _, resources, _ = bundle
    fake = runpy.run_path(str(REPO / 'tests/test_phone_launch.py'))['FAKE_HELPER']
    (resources / 'phone_server.py').write_text(fake)
    shutil.copy2(REPO / 'desktop/phone_launch.py', resources / 'phone_launch.py')
    (resources / 'game/index.html').write_text('<script src="assets/phone-board.js"></script>')
    (resources / 'game/assets').mkdir()
    (resources / 'game/assets/phone-board.js').write_text('// board adapter')
    (resources / 'game/assets/phone-host.html').write_text('<title>Phone host</title>')
    first = run_launch(launcher(), bundle, started_engines)
    assert '#ff_board=' in first['url']
    second = run_launch(launcher(), bundle, started_engines)
    assert second['url'] == first['url']
    assert second['relay_pid'] == first['relay_pid']


def test_phone_bundle_reusing_older_game_keeps_local_controls_and_files(bundle, started_engines):
    import runpy
    _, resources, home = bundle
    fake = runpy.run_path(str(REPO / 'tests/test_phone_launch.py'))['FAKE_HELPER']
    (resources / 'phone_server.py').write_text(fake)
    shutil.copy2(REPO / 'desktop/phone_launch.py', resources / 'phone_launch.py')
    first = run_launch(launcher(), bundle, started_engines)
    assert '#ff_board=' not in first['url']
    assert (home / 'Library/Application Support/Fright Feud/apps/fright-feud/index.html').read_text() == 'bundled game'


def test_existing_engine_game_is_used_without_copying_game(bundle, started_engines):
    module = launcher()
    _, _, home = bundle
    with ExistingEngine(home / "apps") as existing:
        result = run_launch(module, bundle, started_engines, preferred_port=existing.port)
        assert result["reused_engine"] is True
        assert result["installed_game"] is False
        assert result["pid"] is None
        assert existing.refreshes == 0
        assert not (home / "apps").exists()


@pytest.mark.parametrize("route,game", [
    ("/api/apps", True),
    ("/api/app-engine/studio/roots", False),
    ("/api/app-engine/catalog/refresh", False),
])
def test_existing_engine_with_slow_catalog_is_reused(bundle, started_engines, route, game):
    _, _, home = bundle
    root = home / "Existing Apps"
    root.mkdir()
    # A populated real engine can take over a second to enumerate its apps.
    # Keep identity probing fast while allowing actual catalog work to finish.
    with ExistingEngine(root, game=game, delays={route: 1.1}) as existing:
        result = run_launch(launcher(), bundle, started_engines, preferred_port=existing.port)
        assert result["reused_engine"] is True
        assert result["engine_port"] == existing.port
        assert result["installed_game"] is not game
        assert existing.refreshes == (0 if game else 1)


def test_existing_engine_receives_missing_game_and_preserves_existing_files(bundle, started_engines):
    module = launcher()
    _, _, home = bundle
    root = home / "My Games"
    root.mkdir()
    with ExistingEngine(root, game=False) as existing:
        result = run_launch(module, bundle, started_engines, preferred_port=existing.port)
        assert result["installed_game"] is True
        assert result["reused_engine"] is True
        assert existing.refreshes == 1
        (root / "fright-feud/index.html").write_text("user's custom game")
        second = run_launch(module, bundle, started_engines, preferred_port=existing.port)
        assert second["installed_game"] is False
        assert (root / "fright-feud/index.html").read_text() == "user's custom game"


def test_saved_preferences_port_is_discovered(bundle, started_engines):
    module = launcher()
    _, _, home = bundle
    with ExistingEngine(home / "apps") as existing:
        preferences = home / "Library/Preferences/io.appengine.desktop.plist"
        preferences.parent.mkdir(parents=True)
        preferences.write_bytes(plistlib.dumps({"launcherSettings": json.dumps({"enginePort": existing.port}).encode()}))
        result = run_launch(module, bundle, started_engines)
        assert result["reused_engine"] is True
        assert result["engine_port"] == existing.port


def test_occupied_non_engine_port_is_preserved(bundle, started_engines):
    module = launcher()
    _, _, home = bundle
    with ExistingEngine(home / "apps", name="unrelated-service") as unrelated:
        result = run_launch(module, bundle, started_engines, preferred_port=unrelated.port)
        assert result["reused_engine"] is False
        assert result["engine_port"] != unrelated.port
        assert unrelated.refreshes == 0


def test_unrelated_same_name_application_is_never_replaced(bundle, started_engines):
    module = launcher()
    _, _, home = bundle
    destination = home / "Applications/Fright Feud.app/Contents"
    destination.mkdir(parents=True)
    original = plistlib.dumps({"CFBundleIdentifier": "someone.else.game"})
    (destination / "Info.plist").write_bytes(original)
    with pytest.raises(module.LauncherError, match="unrelated|identifier|belongs"):
        run_launch(module, bundle, started_engines)
    assert (destination / "Info.plist").read_bytes() == original


def test_unrelated_same_name_game_is_never_replaced(bundle, started_engines):
    module = launcher()
    _, _, home = bundle
    root = home / "apps"
    game = root / "fright-feud"
    game.mkdir(parents=True)
    (game / "app.json").write_text('{"id":"other"}')
    (game / "index.html").write_text("keep me")
    with ExistingEngine(root, game=False) as existing:
        with pytest.raises(module.LauncherError, match="existing|unrelated|belongs"):
            run_launch(module, bundle, started_engines, preferred_port=existing.port)
    assert (game / "index.html").read_text() == "keep me"


def test_concurrent_clicks_start_one_engine(bundle, started_engines):
    module = launcher()
    preferred = free_port()
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(run_launch, module, bundle, started_engines, preferred_port=preferred) for _ in range(2)]
        results = [future.result() for future in futures]
    assert results[0]["url"] == results[1]["url"]
    assert sum(not result["reused_engine"] for result in results) == 1
    assert len(set(started_engines)) == 2
    assert len({result["relay_pid"] for result in results}) == 1


@pytest.mark.parametrize("url", ["https://evil.example/apps/fright-feud/", "http://fright-feud.localhost:1/apps/fright-feud/", "http://127.0.0.1:8770/apps/other/", "http://user:pass@localhost:8770/apps/fright-feud/"])
def test_spoofed_app_urls_are_rejected(bundle, started_engines, url):
    module = launcher()
    _, _, home = bundle
    with ExistingEngine(home / "apps", url=url) as existing:
        with pytest.raises(module.LauncherError, match="URL|url"):
            run_launch(module, bundle, started_engines, preferred_port=existing.port)


def test_missing_game_in_bundle_fails_before_starting_process(bundle, started_engines):
    module = launcher()
    _, resources, _ = bundle
    (resources / "game/index.html").unlink()
    with pytest.raises(module.LauncherError, match="incomplete|missing|index.html"):
        run_launch(module, bundle, started_engines)


def test_bad_bundle_metadata_is_rejected(bundle, started_engines):
    module = launcher()
    _, resources, _ = bundle
    (resources / "bundle.json").write_text('{"version":"../../escape", "game_id":"other", "engine_commit":"bad"}')
    with pytest.raises(module.LauncherError, match="metadata|bundle|game"):
        run_launch(module, bundle, started_engines)


def test_unusable_external_roots_fall_back_to_bundled_engine(bundle, started_engines, tmp_path):
    module = launcher()
    _, _, home = bundle
    outside = tmp_path / "Not User Home"
    outside.mkdir()
    with ExistingEngine(outside, game=False) as existing:
        result = run_launch(module, bundle, started_engines, preferred_port=existing.port)
        assert result["reused_engine"] is False
        assert not (outside / "fright-feud").exists()


def test_managed_engine_ignores_inherited_public_configuration(bundle, started_engines, monkeypatch):
    module = launcher()
    for key, value in {"APP_ENGINE_PUBLIC_ORIGIN":"https://evil.example", "APP_ENGINE_APP_ORIGINS":"same", "APP_ENGINE_TRUST_PROXY":"1", "APP_ENGINE_PUBLIC_APPS":"other", "APP_ENGINE_ADMIN_SECRET":"inherited-secret"}.items():
        monkeypatch.setenv(key, value)
    result = run_launch(module, bundle, started_engines)
    from urllib.request import urlopen
    from urllib.parse import urlsplit
    port = result["engine_port"]
    with urlopen(f"http://127.0.0.1:{port}/environment") as response:
        env = json.load(response)
    assert env["APP_ENGINE_HOST"] == "127.0.0.1"
    assert not ({"APP_ENGINE_PUBLIC_ORIGIN", "APP_ENGINE_APP_ORIGINS", "APP_ENGINE_TRUST_PROXY", "APP_ENGINE_PUBLIC_APPS", "APP_ENGINE_ADMIN_SECRET"} & env.keys())


def test_failed_engine_reports_log_and_returns_cli_json(bundle):
    app, resources, home = bundle
    (resources / "engine/engine.py").write_text('raise RuntimeError("test startup failure")')
    path = REPO / "desktop/launcher.py"
    assert path.exists(), "The desktop launcher coordinator must exist"
    result = subprocess.run([sys.executable, "-I", "-B", str(path), "--resources", str(resources), "--home", str(home), "--port", str(free_port()), "--bundle", str(app)], capture_output=True, text=True, timeout=15)
    assert result.returncode != 0
    events = [json.loads(line) for line in result.stdout.splitlines()]
    assert events[-1]["event"] == "error"
    assert "log" in events[-1]["message"].lower()
    assert "test startup failure" in (home / "Library/Application Support/Fright Feud/logs/engine.log").read_text()


def test_stopped_saved_external_engine_is_started_without_bundled_fallback(bundle, started_engines):
    module = launcher()
    _, _, home = bundle
    repo = home / "Existing Engine"
    (repo / ".venv/bin").mkdir(parents=True)
    (repo / "engine.py").write_text(FAKE_ENGINE)
    (repo / ".venv/bin/python").symlink_to(sys.executable)
    apps = home / "Existing Apps"
    (apps / "fright-feud").mkdir(parents=True)
    (apps / "fright-feud/app.json").write_text('{"id":"fright-feud","version":"1.0.0"}')
    (apps / "fright-feud/index.html").write_text("old installed game")
    port = free_port()
    preferences = home / "Library/Preferences/io.appengine.desktop.plist"
    preferences.parent.mkdir(parents=True)
    preferences.write_bytes(plistlib.dumps({"launcherSettings": json.dumps({"enginePort": port, "engineRepository": str(repo), "appsDirectory": str(apps)}).encode()}))
    result = run_launch(module, bundle, started_engines, preferred_port=port)
    assert result["installed_game"] is False
    assert result["reused_engine"] is False  # The engine was stopped.
    assert (apps / "fright-feud/index.html").read_text() == "old installed game"
    assert (home / "Library/Application Support/Fright Feud/releases").is_dir()
    remembered = json.loads((home / "Library/Application Support/Fright Feud/engine.json").read_text())
    assert remembered["repository"] == str(repo)


def test_explicit_port_does_not_probe_default_production_port(bundle, started_engines, monkeypatch):
    module = launcher()
    seen = []
    original = module._request
    def observe(port, path, *args, **kwargs):
        seen.append(port)
        return original(port, path, *args, **kwargs)
    monkeypatch.setattr(module, "_request", observe)
    run_launch(module, bundle, started_engines)
    assert 8770 not in seen


@pytest.mark.parametrize("suffix", ["?next=https://evil.example", "#other=value", "#atrium_state_token=x&redirect=y", "#atrium_state_token=%0Aevil"])
def test_game_url_rejects_query_or_unexpected_fragment(bundle, started_engines, suffix):
    module = launcher()
    _, _, home = bundle
    with ExistingEngine(home / "apps") as existing:
        existing.url = f"http://fright-feud.localhost:{existing.port}/apps/fright-feud/{suffix}"
        with pytest.raises(module.LauncherError, match="URL"):
            run_launch(module, bundle, started_engines, preferred_port=existing.port)


def test_partial_owned_application_is_repaired_from_good_download(bundle, started_engines):
    module = launcher()
    _, _, home = bundle
    contents = home / "Applications/Fright Feud.app/Contents"
    contents.mkdir(parents=True)
    (contents / "Info.plist").write_bytes(plistlib.dumps({"CFBundleIdentifier": "com.yongk802.fright-feud"}))
    run_launch(module, bundle, started_engines)
    assert (contents / "Resources/game/index.html").read_text() == "bundled game"


def test_partial_durable_installation_is_preserved_and_recovered(bundle, started_engines):
    module = launcher()
    _, resources, home = bundle
    import hashlib
    metadata = json.loads((resources / "bundle.json").read_text())
    signature = hashlib.sha256(json.dumps(metadata, sort_keys=True).encode()).hexdigest()[:16]
    partial = home / "Library/Application Support/Fright Feud/releases" / f"1.1.0-{signature}"
    partial.mkdir(parents=True)
    (partial / "partial-file").write_text("preserve")
    result = run_launch(module, bundle, started_engines)
    assert result["url"]
    assert (partial / "partial-file").read_text() == "preserve"
    assert len(list(partial.parent.glob("*/.complete.json"))) == 1


def stop_test_engine(pid, pids):
    import os
    import signal
    os.kill(pid, signal.SIGTERM)
    os.waitpid(pid, 0)
    pids.remove(pid)


def test_stopped_managed_engine_restarts_and_preserves_installed_game(bundle, started_engines):
    module = launcher()
    _, _, home = bundle
    first = run_launch(module, bundle, started_engines)
    stop_test_engine(first["pid"], started_engines)
    game = home / "Library/Application Support/Fright Feud/apps/fright-feud/index.html"
    game.write_text("installed custom game")
    result = run_launch(module, bundle, started_engines)
    assert result["reused_engine"] is False
    assert result["installed_game"] is False
    assert result["pid"] != first["pid"]
    from urllib.parse import urlsplit
    remembered = json.loads((home / "Library/Application Support/Fright Feud/engine.json").read_text())
    assert remembered["port"] == result["engine_port"]
    assert game.read_text() == "installed custom game"


def test_child_engine_uses_isolated_home(bundle, started_engines):
    module = launcher()
    _, _, home = bundle
    # The fake engine exposes only APP_ENGINE_ variables; inspect the owned PID's
    # environment through a deliberately tiny replacement entrypoint instead.
    app, resources, _ = bundle
    source = (resources / "engine/engine.py").read_text()
    (resources / "engine/engine.py").write_text(source.replace('if k.startswith("APP_ENGINE_")', 'if k == "HOME" or k.startswith("APP_ENGINE_")'))
    result = run_launch(module, bundle, started_engines)
    from urllib.request import urlopen
    from urllib.parse import urlsplit
    with urlopen(f"http://127.0.0.1:{result['engine_port']}/environment") as response:
        env = json.load(response)
    assert env["HOME"] == str(home.resolve())


def test_atomic_publication_does_not_replace_an_empty_unrelated_folder(tmp_path):
    module = launcher()
    source = tmp_path / "source"
    destination = tmp_path / "existing"
    source.mkdir()
    destination.mkdir()
    (source / "ours").write_text("data")
    with pytest.raises(FileExistsError):
        module._copy_new(source, destination)
    assert list(destination.iterdir()) == []
    assert not list(tmp_path.glob(".fright-feud-install-*"))


@pytest.mark.parametrize("subdirectory", ["releases", "logs", "state"])
def test_owned_support_subdirectories_cannot_redirect_writes(bundle, started_engines, tmp_path, subdirectory):
    module = launcher()
    _, _, home = bundle
    support = home / "Library/Application Support/Fright Feud"
    support.mkdir(parents=True)
    unrelated = tmp_path / "Unrelated data"
    unrelated.mkdir()
    (support / subdirectory).symlink_to(unrelated, target_is_directory=True)
    with pytest.raises(module.LauncherError, match="outside|symlink|directory"):
        run_launch(module, bundle, started_engines)
    assert not list(unrelated.iterdir())


def test_owned_bundle_with_missing_native_executable_is_repaired(bundle, started_engines):
    module = launcher()
    app, _, home = bundle
    installed = home / "Applications/Fright Feud.app"
    installed.parent.mkdir()
    shutil.copytree(app, installed, symlinks=True)
    (installed / "Contents/MacOS/FrightFeud").unlink()
    run_launch(module, bundle, started_engines)
    assert (installed / "Contents/MacOS/FrightFeud").is_file()


def test_failed_stopped_external_engine_falls_back_to_bundled_engine(bundle, started_engines):
    module = launcher()
    _, _, home = bundle
    repository = home / "git/app-engine"
    (repository / ".venv/bin").mkdir(parents=True)
    (repository / "engine.py").write_text('raise RuntimeError("incompatible existing engine")')
    (repository / ".venv/bin/python").symlink_to(sys.executable)
    apps = home / "git/personal-apps"
    apps.mkdir()
    result = run_launch(module, bundle, started_engines)
    assert result["reused_engine"] is False
    remembered = json.loads((home / "Library/Application Support/Fright Feud/engine.json").read_text())
    assert "releases" in remembered["repository"]
    assert "incompatible existing engine" in (home / "Library/Application Support/Fright Feud/logs/engine.log").read_text()


def test_existing_engine_gets_durable_numeric_relay_that_repeats_reuse(bundle, started_engines):
    module = launcher()
    _, resources, home = bundle
    with ExistingEngine(home / "apps") as existing:
        first = run_launch(module, bundle, started_engines, preferred_port=existing.port)
        assert first["url"].startswith("http://127.0.0.1:")
        assert first["url"].endswith("/apps/fright-feud/#atrium_state_token=existing")
        assert first["engine_port"] == existing.port
        assert first["pid"] is None
        assert first["relay_pid"] > 0
        state = json.loads((home / "Library/Application Support/Fright Feud/relay.json").read_text())
        assert state["pid"] == first["relay_pid"]
        assert state["engine_port"] == existing.port
        assert state["home"] == str(home.resolve())
        assert list((home / "Library/Application Support/Fright Feud/releases").glob("*/relay.py"))
        installed = home / "Applications/Fright Feud.app/Contents/Resources"
        shutil.rmtree(resources.parent.parent.parent)
        second = module.launch(installed, home, existing.port, install_bundle=False)
        assert second["url"] == first["url"]
        assert second["relay_pid"] == first["relay_pid"]


def test_invalid_saved_relay_nonce_never_reuses_its_pid(bundle, started_engines):
    module = launcher()
    _, _, home = bundle
    first = run_launch(module, bundle, started_engines)
    state_path = home / "Library/Application Support/Fright Feud/relay.json"
    state = json.loads(state_path.read_text())
    state["nonce"] = "wrong-saved-nonce"
    state_path.write_text(json.dumps(state))
    second = run_launch(module, bundle, started_engines)
    assert second["pid"] == first["pid"]
    assert second["relay_pid"] != first["relay_pid"]
    assert second["url"] != first["url"]
    # The earlier helper is not terminated or controlled by the coordinator.
    from urllib.request import urlopen
    with urlopen(f"http://127.0.0.1:{state['port']}/__fright_feud_health") as response:
        assert json.load(response)["nonce"] != state["nonce"]


def test_missing_relay_fails_resource_validation(bundle, started_engines):
    module = launcher()
    _, resources, _ = bundle
    (resources / "relay.py").unlink()
    with pytest.raises(module.LauncherError, match="relay.py"):
        run_launch(module, bundle, started_engines)


def test_relay_startup_failure_reports_its_own_log(bundle, started_engines):
    module = launcher()
    _, resources, home = bundle
    (resources / "relay.py").write_text('raise RuntimeError("relay startup test failure")')
    with ExistingEngine(home / "apps") as existing:
        with pytest.raises(module.LauncherError, match=r"[Rr]elay.*log|log.*relay"):
            run_launch(module, bundle, started_engines, preferred_port=existing.port)
    assert "relay startup test failure" in (home / "Library/Application Support/Fright Feud/logs/relay.log").read_text()


def test_relay_accepts_a_nonce_starting_with_dash(bundle, started_engines, monkeypatch):
    module = launcher()
    _, _, home = bundle
    nonce = "-leading_dash_valid_nonce_1234567890"
    monkeypatch.setattr(module.secrets, "token_urlsafe", lambda size: nonce)
    with ExistingEngine(home / "apps") as existing:
        result = run_launch(module, bundle, started_engines, preferred_port=existing.port)
        assert result["url"].startswith("http://127.0.0.1:")
        state = json.loads((home / "Library/Application Support/Fright Feud/relay.json").read_text())
        assert state["nonce"] == nonce
        assert state["pid"] == result["relay_pid"]
