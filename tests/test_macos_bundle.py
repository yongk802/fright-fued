"""Release bundle safety checks; native tests run on a Mac with Xcode CLI tools."""
import hashlib
import importlib.util
import io
import json
import platform
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


def builder():
    path = ROOT / 'scripts/build_macos.py'
    if not path.exists():
        raise AssertionError('offline Mac builder is missing')
    spec = importlib.util.spec_from_file_location('build_macos', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class BundleTests(unittest.TestCase):
    def test_real_payload_includes_phone_service_and_browser_assets(self):
        with tempfile.TemporaryDirectory() as folder:
            resources = Path(folder)
            hashes = builder().copy_payload(resources)
            self.assertIn('phone_server.py', hashes)
            self.assertIn('phone_launch.py', hashes)
            self.assertIn('game/assets/phone-board.js', hashes)
            self.assertIn('game/assets/phone-host.html', hashes)

    def test_checksum_rejects_modified_download(self):
        build = builder()
        with tempfile.TemporaryDirectory() as folder:
            archive = Path(folder) / 'runtime.tar.gz'
            archive.write_bytes(b'original runtime')
            digest = hashlib.sha256(archive.read_bytes()).hexdigest()
            build.verify_sha256(archive, digest)
            archive.write_bytes(b'modified runtime')
            with self.assertRaisesRegex(ValueError, 'checksum'):
                build.verify_sha256(archive, digest)

    def test_archive_rejects_escape_before_extracting(self):
        build = builder()
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            archive = root / 'bad.tar'
            with tarfile.open(archive, 'w') as tar:
                entry = tarfile.TarInfo('../escaped')
                entry.size = 3
                tar.addfile(entry, io.BytesIO(b'bad'))
            with self.assertRaisesRegex(ValueError, 'Unsafe'):
                build.extract_archive(archive, root / 'out')
            self.assertFalse((root / 'escaped').exists())

    def test_archive_keeps_internal_python_symlink(self):
        build = builder()
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            archive = root / 'good.tar'
            with tarfile.open(archive, 'w') as tar:
                entry = tarfile.TarInfo('python/bin/python3.12')
                entry.mode, entry.size = 0o755, 3
                tar.addfile(entry, io.BytesIO(b'bin'))
                link = tarfile.TarInfo('python/bin/python3')
                link.type, link.linkname = tarfile.SYMTYPE, 'python3.12'
                tar.addfile(link)
            build.extract_archive(archive, root / 'out')
            self.assertTrue((root / 'out/python/bin/python3').is_symlink())
            self.assertEqual((root / 'out/python/bin/python3').read_bytes(), b'bin')

    def test_archive_rejects_external_symlink(self):
        build = builder()
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            archive = root / 'bad.tar'
            with tarfile.open(archive, 'w') as tar:
                link = tarfile.TarInfo('python/link')
                link.type, link.linkname = tarfile.SYMTYPE, '../../outside'
                tar.addfile(link)
            with self.assertRaisesRegex(ValueError, 'Unsafe'):
                build.extract_archive(archive, root / 'out')

    def test_engine_snapshot_ignores_dirty_worktree(self):
        build = builder()
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            repo = root / 'engine source'
            repo.mkdir()
            def git(*args):
                return subprocess.check_output(['git', '-C', str(repo), *args], text=True).strip()
            git('init', '-q')
            (repo / 'LICENSE').write_text('clean license')
            git('add', '.')
            git('-c', 'user.name=Test', '-c', 'user.email=test@example.org', 'commit', '-qm', 'clean')
            commit = git('rev-parse', 'HEAD')
            (repo / 'LICENSE').write_text('dirty license')
            (repo / 'secret').write_text('not committed')
            build.archive_engine(repo, commit, root / 'snapshot')
            self.assertEqual((root / 'snapshot/LICENSE').read_text(), 'clean license')
            self.assertFalse((root / 'snapshot/secret').exists())

    def test_payload_contains_relay_and_hashes_change_when_payload_changes(self):
        build = builder()
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / 'source'
            (source / 'desktop').mkdir(parents=True)
            (source / 'fonts').mkdir()
            for name in ('launcher.py', 'relay.py'):
                (source / 'desktop' / name).write_text('# ' + name)
            for name in ('app.json', 'index.html', 'THIRD-PARTY-NOTICES.md'):
                (source / name).write_text(name)
            (source / 'fonts/game.woff2').write_bytes(b'font')
            resources = root / 'resources'
            resources.mkdir()
            first = build.copy_payload(resources, source)
            expected = {'launcher.py', 'relay.py', 'game/app.json', 'game/index.html', 'game/THIRD-PARTY-NOTICES.md', 'game/fonts/game.woff2'}
            self.assertEqual(set(first), expected)
            self.assertEqual((resources / 'relay.py').read_text(), '# relay.py')
            for relative, digest in first.items():
                self.assertEqual(hashlib.sha256((resources / relative).read_bytes()).hexdigest(), digest)
            (source / 'desktop/relay.py').write_text('# updated relay')
            updated = root / 'updated'
            updated.mkdir()
            second = build.copy_payload(updated, source)
            self.assertNotEqual(first['relay.py'], second['relay.py'])
            self.assertEqual(first['game/app.json'], second['game/app.json'])

    def test_locked_manifest_has_both_architectures_and_official_hashes(self):
        lock = json.loads((ROOT / 'desktop/runtime-lock.json').read_text())
        self.assertEqual(set(lock['runtimes']), {'arm64', 'x86_64'})
        for arch, entry in lock['runtimes'].items():
            self.assertTrue(entry['url'].startswith('https://github.com/astral-sh/python-build-standalone/releases/download/20261013/'))
            self.assertEqual(len(entry['sha256']), 64)
        self.assertEqual(lock['engine_commit'], 'e81ecafaea1cbbe1af5c4f3b4190ad97776207ad')


@unittest.skipUnless(sys.platform == 'darwin', 'requires macOS AppKit compiler')
class NativeURLTests(unittest.TestCase):
    def test_allows_only_exact_phone_board_fragment(self):
        for fragment in ('ff_board=abc_123-XYZ', 'ff_board=abc&evil=true', 'ff_board=', 'ff_board=abc%0A'):
            result = subprocess.run([str(self.binary), '--validate-url',
                                     'http://127.0.0.1:19990/apps/fright-feud/#' + fragment], capture_output=True)
            self.assertEqual(result.returncode, 0 if fragment == 'ff_board=abc_123-XYZ' else 1)

    @classmethod
    def setUpClass(cls):
        cls.folder = tempfile.TemporaryDirectory()
        cls.binary = Path(cls.folder.name) / 'FrightFeud'
        source = ROOT / 'desktop/FrightFeud.swift'
        if not source.exists():
            raise AssertionError('native Mac launcher is missing')
        subprocess.run(['xcrun', 'swiftc', '-swift-version', '5', str(source), '-o', str(cls.binary)], check=True, capture_output=True)

    @classmethod
    def tearDownClass(cls):
        cls.folder.cleanup()

    def native_response(self, source, with_runtime=True):
        with tempfile.TemporaryDirectory(prefix='launcher resources ') as folder:
            resources = Path(folder)
            runtime = resources / 'runtimes' / platform.machine() / 'python/bin'
            runtime.mkdir(parents=True)
            if with_runtime:
                (runtime / 'python3.12').symlink_to(sys.executable)
            (resources / 'launcher.py').write_text(source)
            return subprocess.run([str(self.binary), '--headless', '--resources', str(resources)], capture_output=True, text=True, timeout=10)

    def test_missing_runtime_reports_actionable_error_and_exits(self):
        result = self.native_response('', with_runtime=False)
        self.assertEqual(result.returncode, 1)
        event = json.loads(result.stdout.splitlines()[-1])
        self.assertEqual(event['event'], 'error')
        self.assertIn('bundled Python runtime', event['message'])
        self.assertIn('Application Support/Fright Feud', event['message'])

    def test_subprocess_failure_cannot_leave_progress_running(self):
        result = self.native_response("import sys; sys.stderr.write('coordinator crashed'); sys.exit(7)")
        self.assertEqual(result.returncode, 1)
        self.assertIn('coordinator crashed', result.stdout)

    def test_unsafe_ready_result_never_opens_browser(self):
        result = self.native_response('print(\'{"event":"ready","url":"https://evil.example/"}\')')
        self.assertEqual(result.returncode, 1)
        self.assertIn('unsafe game address', result.stdout)

    def test_successful_headless_handoff_preserves_engine_capability(self):
        payload = {'event': 'ready', 'url': 'http://fright-feud.localhost:19901/apps/fright-feud/#atrium_state_token=abc123', 'pid': None, 'reused_engine': True, 'installed_game': False}
        result = self.native_response('print(' + repr(json.dumps(payload)) + ')')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), payload)

    def test_opens_only_expected_loopback_game(self):
        accepted = ['http://localhost:8770/apps/fright-feud/', 'http://127.0.0.1:19901/apps/fright-feud/', 'http://games.localhost:8770/apps/fright-feud/', 'http://fright-feud.localhost:19937/apps/fright-feud/#atrium_state_token=abc-_012']
        rejected = ['https://evil.example/apps/fright-feud/', 'http://localhost.evil.example:8770/apps/fright-feud/', 'file:///apps/fright-feud/', 'http://user@localhost:8770/apps/fright-feud/', 'http://localhost/apps/fright-feud/', 'http://localhost:8770/apps/other/', 'http://localhost:0/apps/fright-feud/', 'http://localhost:8770/apps/fright-feud/?url=evil', 'http://localhost:8770/apps/fright-feud/#bad', 'http://localhost:8770/apps/fright-feud/#atrium_state_token=', 'http://localhost:8770/apps/fright-feud/#atrium_state_token=abc&url=evil']
        for url in accepted + rejected:
            with self.subTest(url=url):
                result = subprocess.run([str(self.binary), '--validate-url', url], capture_output=True, timeout=5)
                self.assertEqual(result.returncode, 0 if url in accepted else 1)


if __name__ == '__main__':
    unittest.main()
