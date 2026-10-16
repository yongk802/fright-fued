"""Verify the Desktop update path uses the installed bundled runtime safely."""
import importlib.util
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


def entrypoint():
    path = ROOT / 'scripts/launch_phone.py'
    assert path.exists(), 'Desktop phone entrypoint is missing'
    spec = importlib.util.spec_from_file_location('launch_phone_test', path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


class PhoneEntrypointTests(unittest.TestCase):
    def test_native_ready_selects_only_valid_loopback_game(self):
        value = {'event': 'ready', 'url': 'http://127.0.0.1:19001/apps/fright-feud/', 'engine_port': 19002}
        result = entrypoint().native_ready(json.dumps({'event': 'status', 'message': 'Starting'}) + '\n' + json.dumps(value))
        self.assertEqual(result['engine_port'], 19002)

    def test_native_errors_and_unsafe_ready_never_open_a_browser(self):
        for value in ({'event': 'error', 'message': 'Engine failed'},
                      {'event': 'ready', 'url': 'https://example.org/', 'engine_port': 19002},
                      {'event': 'ready', 'url': 'http://127.0.0.1:19001/api/engine', 'engine_port': 19002},
                      {'event': 'ready', 'url': 'http://127.0.0.1:19001/apps/fright-feud/', 'engine_port': True}):
            with self.assertRaises(RuntimeError):
                entrypoint().native_ready(json.dumps(value))

    def test_desktop_launcher_uses_signed_runtime_and_phone_entrypoint(self):
        with tempfile.TemporaryDirectory(prefix='phone shortcut ') as folder:
            root = Path(folder)
            source = root / 'Desktop Source'
            (source / 'scripts').mkdir(parents=True)
            shutil.copy2(ROOT / 'Launch Fright Feud.command', source / 'Launch.command')
            (source / 'scripts/mac-update.sh').write_text('#!/bin/bash\nexit 0\n')
            (source / 'scripts/launch_phone.py').write_text('# fixture entrypoint')
            runtime = root / 'Applications/Fright Feud.app/Contents/Resources/runtimes' / platform.machine() / 'python/bin'
            runtime.mkdir(parents=True)
            python = runtime / 'python3.12'
            python.write_text('#!/bin/bash\nprintf "%s\\n" "$@" > "$HOME/invocation"\n')
            python.chmod(0o755)
            result = subprocess.run(['bash', str(source / 'Launch.command')],
                                    env={**os.environ, 'HOME': str(root)}, capture_output=True, text=True, timeout=5)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual((root / 'invocation').read_text().splitlines(),
                             ['-I', '-B', str(source / 'scripts/launch_phone.py'), '--app', str(root / 'Applications/Fright Feud.app')])


if __name__ == '__main__':
    unittest.main()
