#!/usr/bin/env python3
"""Desktop shortcut handoff: installed App Engine plus paired phone support."""
import argparse
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]


def native_ready(output):
    result = None
    for line in output.splitlines():
        try:
            event = json.loads(line)
        except ValueError as error:
            raise RuntimeError('The Mac launcher returned an unreadable response.') from error
        if event.get('event') == 'error':
            raise RuntimeError(event.get('message', 'The Mac launcher failed.'))
        if event.get('event') == 'ready':
            result = event
    if result is None:
        raise RuntimeError('The Mac launcher did not return a game address.')
    try:
        url = urlsplit(result.get('url', ''))
        port = result.get('engine_port')
        if (url.scheme != 'http' or url.hostname != '127.0.0.1' or not url.port
                or url.path != '/apps/fright-feud/' or url.username or url.password or url.query
                or type(port) is not int or not 1024 <= port <= 65535):
            raise ValueError('Unsafe game address')
    except ValueError as error:
        raise RuntimeError('The Mac launcher returned an invalid game address.') from error
    return result


def launch(app, home, open_browser=True, port=None):
    executable = app / 'Contents/MacOS/FrightFeud'
    # Headless runs the same signed native coordinator, without opening a second
    # browser tab before the phone-enabled connection has been prepared.
    command = [str(executable), '--headless', '--home', str(home)]
    if port is not None:
        command.extend(['--port', str(port)])
    process = subprocess.run(command,
                             stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=160)
    if process.returncode:
        try:
            native_ready(process.stdout)
        except RuntimeError as error:
            raise RuntimeError(str(error)) from error
        raise RuntimeError('Fright Feud could not start. Reopen the app to try again.')
    ready = native_ready(process.stdout)
    path = ROOT / 'desktop/phone_launch.py'
    spec = importlib.util.spec_from_file_location('fright_feud_phone_launch', path)
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    if not helper.phone_supported(ready['engine_port']):
        raise RuntimeError('The installed game has not updated for phone hosting. Connect to the internet and relaunch the Desktop shortcut.')
    result = helper.ensure_phone(ready['engine_port'], Path(sys.executable), ROOT / 'desktop/phone_server.py',
                                 home / 'Library/Application Support/Fright Feud')
    if open_browser:
        subprocess.run(['/usr/bin/open', result['url']], check=True)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--home', type=Path, default=Path.home())
    parser.add_argument('--app', type=Path)
    parser.add_argument('--no-open', action='store_true')
    parser.add_argument('--port', type=int, help='Explicit isolated engine port for development/testing')
    args = parser.parse_args()
    app = args.app or args.home / 'Applications/Fright Feud.app'
    try:
        result = launch(app, args.home, not args.no_open, args.port)
        print(json.dumps({'event': 'ready', **result}))
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        print('Could not prepare the phone connection: ' + str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
