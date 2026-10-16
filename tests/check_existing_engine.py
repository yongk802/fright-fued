"""Verify the complete Mac app installs into a running engine and serializes clicks."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
from urllib.error import HTTPError
from urllib.parse import urlparse
from urllib.request import urlopen

from check_macos_distribution import events, free_port, ready, stop_owned


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--arch", choices=["arm64", "x86_64"], default="arm64")
    args = parser.parse_args()
    bundle = args.bundle.resolve()
    resources = bundle / "Contents/Resources"
    root = Path(tempfile.mkdtemp(prefix="fright-feud existing engine with spaces-"))
    owned = set()
    process = None
    try:
        home = root / "existing user"
        collection, state = home / "collection", home / "state"
        collection.mkdir(parents=True)
        port = free_port()
        environment = {key: value for key, value in os.environ.items()
                       if not key.startswith(("APP_ENGINE_", "PYTHON")) and key != "VIRTUAL_ENV"}
        environment.update(HOME=str(home), APP_ENGINE_APPS_DIR=str(collection), APP_ENGINE_STATE_DIR=str(state),
                           APP_ENGINE_HOST="127.0.0.1", APP_ENGINE_PORT=str(port))
        python = resources / "runtimes" / args.arch / "python/bin/python3.12"
        with (root / "external-engine.log").open("w") as log:
            process = subprocess.Popen([str(python), "-s", "-B", str(resources / "engine/engine.py")],
                                       cwd=resources / "engine", env=environment, stdout=log, stderr=log)
        for _ in range(100):
            if process.poll() is not None:
                raise AssertionError((root / "external-engine.log").read_text())
            try:
                urlopen(f"http://127.0.0.1:{port}/api/engine", timeout=1).close()
                break
            except OSError:
                time.sleep(.1)
        else:
            raise AssertionError("Disposable existing engine did not start")
        command = ["/usr/bin/arch", "-" + args.arch, str(bundle / "Contents/MacOS/FrightFeud"),
                   "--headless", "--home", str(home), "--port", str(port)]
        first = ready(command)
        owned.add(first["relay_pid"])
        if first.get("pid"):
            owned.add(first["pid"])
        assert first["reused_engine"] and first["installed_game"] and first["pid"] is None, first
        assert first["engine_port"] == port
        index = collection / "fright-feud/index.html"
        assert index.is_file()
        edited = index.read_text() + "\n<!-- locally edited, preserve this -->\n"
        index.write_text(edited)
        second = ready(command)
        assert second["reused_engine"] and not second["installed_game"], second
        assert second["relay_pid"] == first["relay_pid"] and index.read_text() == edited
        address = urlparse(first["url"])
        with urlopen(first["url"].split("#")[0], timeout=3) as response:
            assert b"Fright Feud" in response.read()
        try:
            urlopen(f"http://127.0.0.1:{address.port}/api/engine", timeout=3)
            raise AssertionError("Relay exposed engine controls")
        except HTTPError as error:
            assert error.code == 404
        # An independent fresh install receives two simultaneous native clicks.
        concurrent_home = root / "concurrent user"
        concurrent_port = free_port()
        parallel = ["/usr/bin/arch", "-" + args.arch, str(bundle / "Contents/MacOS/FrightFeud"),
                    "--headless", "--home", str(concurrent_home), "--port", str(concurrent_port)]
        children = [subprocess.Popen(parallel, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) for _ in range(2)]
        results = []
        for child in children:
            output, errors = child.communicate(timeout=120)
            assert child.returncode == 0, (output, errors)
            result = next(value for value in events(output) if value.get("event") == "ready")
            results.append(result)
            owned.update(value for key in ("pid", "relay_pid") if (value := result.get(key)))
        assert results[0]["pid"] == results[1]["pid"] and results[0]["relay_pid"] == results[1]["relay_pid"]
        assert sorted(value["installed_game"] for value in results) == [False, True]
        print(json.dumps({"result": "PASS", "existing_engine_install": True, "edited_game_preserved": True,
                          "engine_controls_denied": True, "concurrent_clicks_single_engine": True}, indent=2))
    finally:
        for pid in owned:
            stop_owned(pid)
        if process is not None:
            process.terminate()
            process.wait(timeout=10)
        shutil.rmtree(root)


if __name__ == "__main__":
    main()
