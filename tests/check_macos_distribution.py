"""Qualify the built Mac app without touching the real user's engine or home.

Run with a built or ZIP-extracted .app. Native headless mode tests the same
coordinator used by the graphical launcher, while suppressing browser opening.
"""
import argparse
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import tempfile
import time
from urllib.parse import urlparse
from urllib.request import urlopen


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def events(output):
    parsed = []
    for line in output.splitlines():
        try:
            value = json.loads(line)
        except ValueError:
            continue
        if isinstance(value, dict):
            parsed.append(value)
    return parsed


def ready(command):
    result = subprocess.run(command, capture_output=True, text=True, timeout=120)
    messages = events(result.stdout)
    assert result.returncode == 0, (result.returncode, result.stdout, result.stderr)
    matches = [message for message in messages if message.get("event") == "ready"]
    assert matches, (result.stdout, result.stderr)
    return matches[-1]


def stop_owned(pid):
    if not pid:
        return
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    for _ in range(50):
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return
        time.sleep(.1)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--arch", choices=["arm64", "x86_64"], default="arm64")
    parser.add_argument("--artifacts", type=Path, default=Path("test-results/macos"))
    parser.add_argument("--keep-home", action="store_true")
    parser.add_argument("--phone-host", action="store_true", help="Exercise paired phone controls at the native launch URL")
    args = parser.parse_args()
    bundle = args.bundle.resolve()
    args.artifacts.mkdir(parents=True, exist_ok=True)
    args.artifacts = args.artifacts.resolve()
    temporary = Path(tempfile.mkdtemp(prefix="fright-feud install with spaces-"))
    owned = set()
    try:
        port_override = free_port()
        command = ["/usr/bin/arch", "-" + args.arch,
                   str(bundle / "Contents/MacOS/FrightFeud"), "--headless",
                   "--home", str(temporary), "--port", str(port_override)]
        first = ready(command)
        if first.get("pid"):
            owned.add(first["pid"])
        if first.get("relay_pid"):
            owned.add(first["relay_pid"])
        assert not first["reused_engine"], first
        assert first["installed_game"], first
        assert (temporary / "Applications/Fright Feud.app/Contents/Info.plist").is_file()
        port = first.get("engine_port") or urlparse(first["url"]).port
        assert port and port != 8770, first
        base = f"http://127.0.0.1:{port}"
        with urlopen(base + "/api/engine", timeout=3) as response:
            assert json.load(response)["name"] == "app-engine"
        installed_executable = temporary / "Applications/Fright Feud.app/Contents/MacOS/FrightFeud"
        installed_command = ["/usr/bin/arch", "-" + args.arch, str(installed_executable),
                             "--headless", "--home", str(temporary), "--port", str(port_override)]
        second = ready(installed_command)
        assert second["reused_engine"] and not second["installed_game"], second
        assert second["url"] == first["url"], (first, second)
        # Playwright is a development dependency, deliberately absent from the app.
        developer_python = os.environ.get("FRIGHT_FEUD_TEST_PYTHON", sys.executable)
        if args.phone_host:
            browser_check = [developer_python, str(Path(__file__).with_name("check_phone_host.py")),
                             "--url", first["url"], "--screenshots", str(args.artifacts / args.arch)]
        else:
            browser_check = [developer_python, str(Path(__file__).with_name("check_app_engine.py")),
                             "--url", base, "--game-url", first["url"],
                             "--screenshots", str(args.artifacts / args.arch)]
        subprocess.run(browser_check, check=True)
        native = ready(["/usr/bin/arch", "-" + args.arch, str(installed_executable), "--headless",
                        "--home", str(temporary), "--port", str(port)])
        assert native["reused_engine"], native
        stop_owned(first.get("pid"))
        owned.discard(first.get("pid"))
        restarted = ready(installed_command)
        if restarted.get("pid"):
            owned.add(restarted["pid"])
        if restarted.get("relay_pid"):
            owned.add(restarted["relay_pid"])
        assert not restarted["reused_engine"] and not restarted["installed_game"], restarted
        report = {"result": "PASS", "arch": args.arch, "first": first,
                  "repeat": second, "native": native, "restart": restarted,
                  "temporary_home": str(temporary)}
        # Capabilities in URL fragments are ephemeral engine-local state, not logs.
        for key in ("first", "repeat", "native", "restart"):
            report[key]["url"] = report[key]["url"].split("#", 1)[0]
        (args.artifacts / (args.arch + "-result.json")).write_text(json.dumps(report, indent=2) + "\n")
        print(json.dumps(report, indent=2))
    finally:
        for pid in owned:
            stop_owned(pid)
        if not args.keep_home:
            import shutil
            shutil.rmtree(temporary)


if __name__ == "__main__":
    main()
