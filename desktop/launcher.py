#!/usr/bin/env python3
"""Offline macOS install/lifecycle coordinator. Uses only the Python standard library.

The native launcher consumes newline-delimited JSON on stdout. Engine output goes
only to the durable log; no subprocess inherits the native launcher's pipe.
"""
from __future__ import annotations

import argparse
import ctypes
import fcntl
import hashlib
import json
import os
from pathlib import Path
import platform
import plistlib
import re
import secrets
import shutil
import socket
import subprocess
import tempfile
import time
from typing import Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener
import uuid

BUNDLE_ID = "com.yongk802.fright-feud"
GAME_ID = "fright-feud"
SUPPORT_PATH = Path("Library/Application Support/Fright Feud")
MAX_JSON_BYTES = 2 * 1024 * 1024


class LauncherError(RuntimeError):
    """An actionable installation, engine, or resource failure."""


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _emit(event: str, **values) -> None:
    print(json.dumps({"event": event, **values}, ensure_ascii=False), flush=True)


def _json_file(path: Path) -> dict:
    try:
        if path.stat().st_size > MAX_JSON_BYTES:
            raise ValueError("JSON file is too large")
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("expected a JSON object")
        return data
    except (OSError, ValueError, UnicodeError) as exc:
        raise LauncherError(f"Cannot read {path}: {exc}") from exc


def _architecture() -> str:
    machine = platform.machine().lower()
    if machine in {"arm64", "aarch64"}:
        return "arm64"
    if machine in {"x86_64", "amd64"}:
        return "x86_64"
    raise LauncherError(f"This app does not include a Python runtime for {machine}.")


def _validate_resources(resources: Path) -> dict:
    metadata = _json_file(resources / "bundle.json")
    version = metadata.get("version")
    commit = metadata.get("engine_commit")
    if (metadata.get("game_id") != GAME_ID
            or not isinstance(version, str)
            or not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+(?:[-+][A-Za-z0-9.-]+)?", version)
            or not isinstance(commit, str)
            or not re.fullmatch(r"[a-fA-F0-9]{7,64}", commit)):
        raise LauncherError("The bundled metadata is invalid. Download Fright Feud again.")
    required = ["relay.py", "engine/engine.py", "game/app.json", "game/index.html",
                f"runtimes/{_architecture()}/python/bin/python3.12"]
    for relative in required:
        if not (resources / relative).is_file():
            raise LauncherError(f"The app bundle is incomplete: missing {relative}. Download it again.")
    runtime = resources / required[-1]
    if not os.access(runtime, os.X_OK):
        raise LauncherError(f"The bundled Python is not executable: {runtime}. Extract the original ZIP again.")
    if _json_file(resources / "game/app.json").get("id") != GAME_ID:
        raise LauncherError("The bundled game manifest has an unexpected game ID.")
    return metadata


def _is_within(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except (ValueError, OSError):
        return False


def _owned_directory(path: Path, home: Path) -> None:
    # Do not follow relocated support/apps directories outside the user's home.
    if path.is_symlink() or not _is_within(path, home):
        raise LauncherError(f"The installation directory is a symlink or points outside your home: {path}")
    path.mkdir(parents=True, exist_ok=True)


def _rename_new(source: Path, destination: Path) -> None:
    """Atomically publish a directory without replacing even an empty directory."""
    libc = ctypes.CDLL(None, use_errno=True)
    if platform.system() == "Darwin":
        rename = libc.renamex_np
        rename.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_uint]
        result = rename(os.fsencode(source), os.fsencode(destination), 0x00000004)  # RENAME_EXCL
    elif hasattr(libc, "renameat2"):
        rename = libc.renameat2
        rename.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
        result = rename(-100, os.fsencode(source), -100, os.fsencode(destination), 1)  # RENAME_NOREPLACE
    else:
        raise LauncherError("This operating system cannot safely install the app atomically.")
    if result:
        code = ctypes.get_errno()
        raise OSError(code, os.strerror(code), str(destination))


def _copy_new(source: Path, destination: Path, validate=None) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=".fright-feud-install-", dir=destination.parent))
    try:
        shutil.copytree(source, stage, symlinks=True, dirs_exist_ok=True)
        if validate:
            validate(stage)
        _rename_new(stage, destination)
    finally:
        if stage.exists():
            shutil.rmtree(stage)


def _bundle_identifier(bundle: Path) -> str | None:
    try:
        with (bundle / "Contents/Info.plist").open("rb") as stream:
            metadata = plistlib.load(stream)
        return metadata.get("CFBundleIdentifier") if isinstance(metadata, dict) else None
    except (OSError, ValueError, plistlib.InvalidFileException):
        return None


def _validate_app_bundle(bundle: Path) -> None:
    if _bundle_identifier(bundle) != BUNDLE_ID:
        raise LauncherError("The source app has an unexpected bundle identifier. Download Fright Feud again.")
    with (bundle / "Contents/Info.plist").open("rb") as stream:
        executable = plistlib.load(stream).get("CFBundleExecutable")
    if (not isinstance(executable, str) or executable in {"", ".", ".."}
            or Path(executable).name != executable
            or not (bundle / "Contents/MacOS" / executable).is_file()
            or not os.access(bundle / "Contents/MacOS" / executable, os.X_OK)):
        raise LauncherError("The app bundle is incomplete: its native launcher is missing. Extract the original ZIP again.")
    _validate_resources(bundle / "Contents/Resources")


def _install_app(bundle: Path, home: Path, status) -> None:
    _validate_app_bundle(bundle)
    destination = home / "Applications/Fright Feud.app"
    _owned_directory(destination.parent, home)
    if destination.exists() or destination.is_symlink():
        if destination.is_symlink() or _bundle_identifier(destination) != BUNDLE_ID:
            raise LauncherError(f"An unrelated app or folder already exists at {destination}. Move it before installing Fright Feud.")
        try:
            _validate_app_bundle(destination)
            return
        except LauncherError:
            status("Repairing the incomplete installed Fright Feud app…")
            # Preserve the damaged owned app instead of deleting files that an
            # already-running native launcher may still be using.
            backup = destination.with_name(f"Fright Feud.incomplete-{uuid.uuid4().hex[:8]}.app")
            _rename_new(destination, backup)
            try:
                _copy_new(bundle, destination, _validate_app_bundle)
            except BaseException:
                if not destination.exists():
                    _rename_new(backup, destination)
                raise
            return
    status("Installing Fright Feud in your Applications folder…")
    _copy_new(bundle, destination, _validate_app_bundle)


def _atomic_json(path: Path, value: dict) -> None:
    fd, name = tempfile.mkstemp(prefix=".state-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(value, stream)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def _optional_json(path: Path) -> dict:
    try:
        return _json_file(path)
    except LauncherError:
        return {}


def _preferences(home: Path) -> dict:
    path = home / "Library/Preferences/io.appengine.desktop.plist"
    try:
        if path.stat().st_size > MAX_JSON_BYTES:
            return {}
        with path.open("rb") as stream:
            plist = plistlib.load(stream)
        raw = plist.get("launcherSettings")
        result = json.loads(raw) if isinstance(raw, (bytes, str)) else {}
        return result if isinstance(result, dict) else {}
    except (OSError, ValueError, AttributeError, plistlib.InvalidFileException):
        return {}


def _port(value) -> int | None:
    return value if type(value) is int and 1024 <= value <= 65535 else None


def _request(port: int, path: str, method: str = "GET", timeout: float = 0.6):
    # Ignore inherited proxy settings and never follow a local server's redirect.
    opener = build_opener(ProxyHandler({}), _NoRedirect())
    request = Request(f"http://127.0.0.1:{port}{path}", method=method,
                      data=b"{}" if method == "POST" else None,
                      headers={"Accept": "application/json", "Content-Type": "application/json"})
    with opener.open(request, timeout=timeout) as response:
        payload = response.read(MAX_JSON_BYTES + 1)
    if len(payload) > MAX_JSON_BYTES:
        raise ValueError("Engine response is too large")
    return json.loads(payload)


def _probe(port: int) -> bool:
    try:
        identity = _request(port, "/api/engine")
        return isinstance(identity, dict) and identity.get("name") == "app-engine"
    except (OSError, ValueError, HTTPError, URLError):
        return False


def _game_url(port: int) -> str | None:
    apps = _request(port, "/api/apps")
    if not isinstance(apps, list):
        raise LauncherError("App Engine returned an invalid app catalog.")
    for item in apps:
        if not isinstance(item, dict) or item.get("id") != GAME_ID:
            continue
        url = item.get("url")
        try:
            parsed = urlsplit(url) if isinstance(url, str) else None
            if (parsed is None or parsed.scheme != "http" or parsed.username is not None
                    or parsed.password is not None or parsed.port != port
                    or parsed.hostname not in {"127.0.0.1", "::1", "localhost", f"{GAME_ID}.localhost"}
                    or parsed.path != f"/apps/{GAME_ID}/"
                    or parsed.query
                    or (parsed.fragment and not re.fullmatch(r"atrium_state_token=[A-Za-z0-9_-]+", parsed.fragment))
                    or any(ord(char) < 32 or char == "\\" for char in url)):
                raise ValueError("unexpected origin or game path")
        except ValueError as exc:
            raise LauncherError("App Engine returned an unsafe game URL. Open App Engine and check its local origin settings.") from exc
        return url
    return None


def _install_game(source: Path, root: Path, home: Path, status) -> bool:
    _owned_directory(root, home)
    destination = root / GAME_ID
    if destination.exists() or destination.is_symlink():
        if (destination.is_symlink() or not destination.is_dir()
                or _optional_json(destination / "app.json").get("id") != GAME_ID):
            raise LauncherError(f"The existing folder {destination} belongs to an unrelated or incomplete game. Move it before trying again.")
        # Installed games, including older versions and user edits, are preserved.
        return False
    status("Installing the Fright Feud game…")
    _copy_new(source, destination)
    return True


def _install_into_running(port: int, source: Path, home: Path, status) -> tuple[str, bool] | None:
    try:
        roots = _request(port, "/api/app-engine/studio/roots")
    except (OSError, ValueError, HTTPError, URLError):
        return None
    if not isinstance(roots, list):
        return None
    for entry in roots:
        if not isinstance(entry, dict) or entry.get("create") is not True or entry.get("write") is not True:
            continue
        raw = entry.get("root")
        if not isinstance(raw, str) or not Path(raw).is_absolute():
            continue
        root = Path(raw)
        if not _is_within(root, home) or not root.is_dir() or not os.access(root, os.W_OK):
            continue
        installed = _install_game(source, root, home, status)
        try:
            _request(port, "/api/app-engine/catalog/refresh", method="POST")
            url = _game_url(port)
        except (OSError, ValueError, HTTPError, URLError) as exc:
            raise LauncherError(f"The game was installed at {root / GAME_ID}, but App Engine could not refresh it: {exc}") from exc
        if url:
            return url, installed
        raise LauncherError(f"App Engine did not discover {root / GAME_ID}. Open App Studio to inspect the existing game; its files were preserved.")
    return None


def _durable_resources(resources: Path, support: Path, metadata: dict, status) -> Path:
    signature = hashlib.sha256(json.dumps(metadata, sort_keys=True).encode()).hexdigest()[:16]
    releases = support / "releases"
    _owned_directory(releases, support.parents[2])
    destination = releases / f"{metadata['version']}-{signature}"
    candidates = [destination, *sorted(releases.glob(f"{metadata['version']}-{signature}-*"))]
    for candidate in candidates:
        if not candidate.is_dir() or candidate.is_symlink():
            continue
        try:
            if (_optional_json(candidate / ".complete.json").get("signature") == signature
                    and _validate_resources(candidate) == metadata):
                return candidate
        except LauncherError:
            pass
    if destination.exists() or destination.is_symlink():
        # Keep damaged/partial directories intact; reuse a complete recovery copy
        # on subsequent launches rather than copying the runtimes again.
        destination = releases / f"{metadata['version']}-{signature}-{uuid.uuid4().hex[:8]}"
    status("Preparing the bundled App Engine and Python runtime…")
    def validate(stage):
        _validate_resources(stage)
        _atomic_json(stage / ".complete.json", {"signature": signature})
    _copy_new(resources, destination, validate)
    return destination


def _bundled_installation(resources: Path, support: Path, metadata: dict, status) -> tuple[Path, Path, Path, Path]:
    durable = _durable_resources(resources, support, metadata, status)
    return (durable / "engine", durable / f"runtimes/{_architecture()}/python/bin/python3.12",
            support / "apps", support / "state")


def _external_installation(settings: dict, home: Path) -> tuple[Path, Path, Path, Path] | None:
    candidates = [(settings.get("engineRepository"), settings.get("appsDirectory"), settings.get("stateDirectory")),
                  (str(home / "git/app-engine"), str(home / "git/personal-apps"), None)]
    for repository, apps, state in candidates:
        if not isinstance(repository, str) or not isinstance(apps, str):
            continue
        repo, root = Path(repository).expanduser(), Path(apps).expanduser()
        state_dir = Path(state).expanduser() if isinstance(state, str) and state else home / ".config/app-engine/app-state"
        python = repo / ".venv/bin/python"
        if (repo.is_absolute() and root.is_absolute() and state_dir.is_absolute()
                and all(_is_within(path, home) for path in (repo, root, state_dir))
                and (repo / "engine.py").is_file() and python.is_file()
                and os.access(python, os.X_OK) and root.is_dir() and os.access(root, os.W_OK)):
            return repo, python, root, state_dir
    return None


def _free_port(preferred: int) -> int:
    for candidate in [preferred, *range(18771, 18871), 0]:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
            try:
                listener.bind(("127.0.0.1", candidate))
            except OSError:
                continue
            return listener.getsockname()[1]
    raise LauncherError("No free local port is available for App Engine.")


def _process_environment(home: Path) -> dict[str, str]:
    environment = {key: value for key, value in os.environ.items()
                   if not key.startswith(("APP_ENGINE_", "PYTHON"))
                   and key not in {"VIRTUAL_ENV", "UV_PROJECT_ENVIRONMENT"}}
    environment.update({"HOME": str(home), "PYTHONDONTWRITEBYTECODE": "1", "PYTHONUNBUFFERED": "1"})
    return environment


def _healthy_relay(state: dict, engine_port: int) -> bool:
    nonce = state.get("nonce")
    port = _port(state.get("port"))
    if (state.get("engine_port") != engine_port or port is None
            or type(state.get("pid")) is not int or state["pid"] <= 0
            or not isinstance(nonce, str) or not re.fullmatch(r"[A-Za-z0-9_-]{16,128}", nonce)):
        return False
    try:
        health = _request(port, "/__fright_feud_health")
        return (isinstance(health, dict) and health.get("name") == "fright-feud-relay"
                and health.get("engine_port") == engine_port and health.get("nonce") == nonce)
    except (OSError, ValueError, HTTPError, URLError):
        return False


def _ensure_relay(engine_port: int, resources: Path, support: Path, metadata: dict,
                  home: Path, timeout: float, status) -> tuple[int, int]:
    # Always run the helper and its interpreter from durable resources, including
    # when the upstream is an already-running external App Engine installation.
    durable = _durable_resources(resources, support, metadata, status)
    state_path = support / "relay.json"
    previous = _optional_json(state_path)
    if _healthy_relay(previous, engine_port):
        return previous["port"], previous["pid"]
    nonce = secrets.token_urlsafe(32)
    logs = support / "logs"
    _owned_directory(logs, home)
    log_path = logs / "relay.log"
    if log_path.is_symlink():
        raise LauncherError(f"The relay log is a symlink: {log_path}")
    python = durable / f"runtimes/{_architecture()}/python/bin/python3.12"
    command = [str(python), "-I", "-B", str(durable / "relay.py"),
               "--engine-port", str(engine_port), "--listen-port", "0",
               "--state-file", str(state_path), "--nonce=" + nonce]
    status("Preparing the local browser connection…")
    try:
        with log_path.open("ab", buffering=0) as log:
            process = subprocess.Popen(command, cwd=durable, env=_process_environment(home),
                                       stdin=subprocess.DEVNULL, stdout=log, stderr=log,
                                       start_new_session=True, close_fds=True)
    except OSError as exc:
        raise LauncherError(f"Could not start the browser relay: {exc}. Log: {log_path}") from exc
    deadline = time.monotonic() + min(timeout, 15.0)
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise LauncherError(f"The browser relay exited before it was ready. Open its log: {log_path}")
        state = _optional_json(state_path)
        if (state.get("nonce") == nonce and state.get("pid") == process.pid
                and _healthy_relay(state, engine_port)):
            return state["port"], process.pid
        time.sleep(0.1)
    # Do not terminate earlier or slow helpers; each helper owns its upstream
    # lifetime, and its random nonce prevents stale state from being trusted.
    raise LauncherError(f"The browser relay did not become ready. Try opening Fright Feud again. Log: {log_path}")


def _ready(engine_url: str, engine_port: int, pid: int | None, reused: bool, installed: bool,
           resources: Path, support: Path, metadata: dict, home: Path, timeout: float, status) -> dict:
    if (resources / 'phone_launch.py').is_file() and (resources / 'phone_server.py').is_file():
        import importlib.util
        durable = _durable_resources(resources, support, metadata, status)
        spec = importlib.util.spec_from_file_location('fright_feud_phone_launch', durable / 'phone_launch.py')
        phone = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(phone)
        if phone.phone_supported(engine_port):
            status('Preparing the game and phone connection…')
            try:
                ready = phone.ensure_phone(engine_port, durable / f'runtimes/{_architecture()}/python/bin/python3.12',
                                           durable / 'phone_server.py', support, timeout)
            except (OSError, ValueError, RuntimeError) as error:
                raise LauncherError(str(error)) from error
            return {'url': ready['url'], 'reused_engine': reused, 'installed_game': installed,
                    'pid': pid, 'engine_port': engine_port, 'relay_pid': ready['pid']}
        status('Keeping your installed game. Use the Desktop shortcut to update it for phone hosting.')
    relay_port, relay_pid = _ensure_relay(engine_port, resources, support, metadata, home, timeout, status)
    fragment = urlsplit(engine_url).fragment
    url = f"http://127.0.0.1:{relay_port}/apps/{GAME_ID}/" + (f"#{fragment}" if fragment else "")
    return {"url": url, "reused_engine": reused, "installed_game": installed, "pid": pid,
            "engine_port": engine_port, "relay_pid": relay_pid}


def _start_engine(repo: Path, python: Path, apps: Path, state: Path, port: int,
                  support: Path, timeout: float, status, home: Path) -> tuple[int, str]:
    logs = support / "logs"
    _owned_directory(logs, home)
    log_path = logs / "engine.log"
    if log_path.is_symlink():
        raise LauncherError(f"The engine log is a symlink: {log_path}")
    _owned_directory(state, home)
    # A Finder-launched app should not inherit another engine's public deployment,
    # credentials, app scan roots, or Python environment configuration.
    environment = _process_environment(home)
    environment.update({"APP_ENGINE_APPS_DIR": str(apps), "APP_ENGINE_STATE_DIR": str(state),
                        "APP_ENGINE_HOST": "127.0.0.1", "APP_ENGINE_PORT": str(port)})
    status("Starting App Engine…")
    try:
        with log_path.open("ab", buffering=0) as log:
            process = subprocess.Popen([str(python), "-s", "-B", str(repo / "engine.py")],
                                       cwd=repo, env=environment, stdin=subprocess.DEVNULL,
                                       stdout=log, stderr=log, start_new_session=True, close_fds=True)
    except OSError as exc:
        raise LauncherError(f"Could not start App Engine: {exc}. Log: {log_path}") from exc
    _atomic_json(support / "engine.json", {"pid": process.pid, "port": port, "repository": str(repo)})
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise LauncherError(f"App Engine exited before it was ready. Open the log for details: {log_path}")
        if _probe(port):
            try:
                url = _game_url(port)
            except (OSError, ValueError, HTTPError, URLError):
                url = None
            if url:
                return process.pid, url
        time.sleep(0.1)
    # Never kill processes, even on timeout; the next click can discover readiness.
    raise LauncherError(f"App Engine did not become ready within {timeout:g} seconds. Try opening Fright Feud again. Log: {log_path}")


def launch(resources: Path, home: Path | None = None, preferred_port: int = 8770, *,
           bundle: Path | None = None, install_bundle: bool = True,
           readiness_timeout: float = 45.0,
           status: Callable[[str], None] | None = None) -> dict:
    """Install/reuse the game and return its validated local URL and launch facts.

    A custom port excludes the default 8770 probe, permitting isolated qualification
    homes. Ports saved in that home's own preferences/state are also considered.
    Raises LauncherError and never terminates an existing process.
    """
    resources = Path(resources).resolve()
    home = Path(home if home is not None else Path.home()).resolve()
    if not _port(preferred_port):
        raise LauncherError("The App Engine port must be between 1024 and 65535.")
    if readiness_timeout <= 0:
        raise LauncherError("The App Engine readiness timeout must be positive.")
    report = status or (lambda message: _emit("status", message=message))
    support = home / SUPPORT_PATH
    try:
        metadata = _validate_resources(resources)
        _owned_directory(support, home)
        with (support / "launcher.lock").open("a+") as lock:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
            if install_bundle and bundle is not None:
                _install_app(Path(bundle).resolve(), home, report)
            settings = _preferences(home)
            remembered = _optional_json(support / "engine.json")
            ports = list(dict.fromkeys(value for value in [
                _port(remembered.get("port")), _port(settings.get("enginePort")), preferred_port,
            ] if value is not None))
            report("Looking for an existing App Engine…")
            for port in ports:
                if not _probe(port):
                    continue
                url = _game_url(port)
                installed = False
                if not url:
                    outcome = _install_into_running(port, resources / "game", home, report)
                    if outcome is None:
                        continue
                    url, installed = outcome
                # A remembered PID is informational only; identity comes from HTTP.
                pid = remembered.get("pid") if port == remembered.get("port") else None
                if type(pid) is not int or pid <= 0:
                    pid = None
                return _ready(url, port, pid, True, installed, resources, support, metadata,
                              home, readiness_timeout, report)
            external = _external_installation(settings, home)
            if external:
                repo, python, apps, state = external
                report("Using your installed App Engine…")
            else:
                repo, python, apps, state = _bundled_installation(resources, support, metadata, report)
            installed = _install_game(resources / "game", apps, home, report)
            port = _free_port(_port(remembered.get("port")) or _port(settings.get("enginePort")) or preferred_port)
            try:
                pid, url = _start_engine(repo, python, apps, state, port, support, readiness_timeout, report, home)
            except LauncherError:
                if not external:
                    raise
                report("Your installed App Engine could not start. Using the bundled App Engine…")
                repo, python, apps, state = _bundled_installation(resources, support, metadata, report)
                installed = _install_game(resources / "game", apps, home, report)
                # A slow external process may still be alive. Leave it alone and
                # select another free port for the complete bundled fallback.
                port = _free_port(port)
                pid, url = _start_engine(repo, python, apps, state, port, support, readiness_timeout, report, home)
            return _ready(url, port, pid, False, installed, resources, support, metadata,
                          home, readiness_timeout, report)
    except LauncherError:
        raise
    except (OSError, ValueError, HTTPError, URLError) as exc:
        raise LauncherError(f"Fright Feud could not finish launching: {exc}. Check available disk space and folder permissions, then try again.") from exc


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Install or open the bundled Fright Feud game")
    parser.add_argument("--resources", type=Path, required=True)
    parser.add_argument("--bundle", type=Path)
    parser.add_argument("--home", type=Path, default=Path.home())
    parser.add_argument("--port", type=int, default=8770)
    parser.add_argument("--no-install-bundle", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = launch(args.resources, args.home, args.port, bundle=args.bundle,
                        install_bundle=not args.no_install_bundle)
    except LauncherError as exc:
        _emit("error", message=str(exc))
        return 1
    _emit("ready", **result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
