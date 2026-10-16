"""Real helper lifecycle checks with isolated homes and test-owned processes."""
import importlib.util
import json
import os
from pathlib import Path
import signal
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = Path(__file__).resolve().parents[1]


def module():
    path = ROOT / 'desktop/phone_launch.py'
    assert path.exists(), 'Phone launch integration is missing'
    spec = importlib.util.spec_from_file_location('phone_launch_test', path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


FAKE_HELPER = '''import argparse, hashlib, json, os
from pathlib import Path
from http.server import BaseHTTPRequestHandler, HTTPServer
p=argparse.ArgumentParser()
for flag in ['engine-port','listen-port','state-file','nonce']: p.add_argument('--'+flag)
a=p.parse_args()
digest=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
class H(BaseHTTPRequestHandler):
 def log_message(self,*args): pass
 def do_GET(self):
  if self.path!='/phone/health' or self.headers.get('Authorization')!='Bearer '+a.nonce:
   self.send_error(403); return
  value=json.dumps(dict(name='fright-feud-phone',version=1,engine_port=int(a.engine_port),nonce=a.nonce,source_sha256=digest)).encode()
  self.send_response(200);self.send_header('Content-Length',str(len(value)));self.end_headers();self.wfile.write(value)
s=HTTPServer(('127.0.0.1',int(a.listen_port)),H)
Path(a.state_file).write_text(json.dumps(dict(pid=os.getpid(),port=s.server_port,engine_port=int(a.engine_port),nonce=a.nonce,source_sha256=digest,version=1)))
s.serve_forever()
'''


class PhoneLaunchTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory(prefix='phone-launch-test-')
        self.root = Path(self.folder.name)
        self.helper = self.root / 'source/phone_server.py'
        self.helper.parent.mkdir()
        self.helper.write_text(FAKE_HELPER)
        self.support = self.root / 'support'
        self.pids = set()

    def tearDown(self):
        for pid in self.pids:
            try:
                os.kill(pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
        self.folder.cleanup()

    def launch(self):
        result = module().ensure_phone(19001, Path(sys.executable), self.helper, self.support, timeout=4)
        self.pids.add(result['pid'])
        return result

    def test_starts_and_reuses_owned_helper_and_private_board_url(self):
        first = self.launch()
        self.assertIn('/apps/fright-feud/#ff_board=', first['url'])
        self.assertTrue(first['url'].startswith('http://127.0.0.1:'))
        second = self.launch()
        self.assertEqual(first, second)
        self.assertEqual((self.support / 'phone.json').stat().st_mode & 0o777, 0o600)

    def test_helper_runs_from_durable_copy_after_source_is_removed(self):
        result = self.launch()
        self.helper.unlink()
        state = json.loads((self.support / 'phone.json').read_text())
        self.assertTrue(module().healthy_phone(state, 19001, state['source_sha256']))
        self.assertEqual(result['pid'], state['pid'])

    def test_source_update_starts_new_helper_without_killing_existing_one(self):
        first = self.launch()
        self.helper.write_text(FAKE_HELPER + '\n# updated\n')
        updated = self.launch()
        self.assertNotEqual(first['pid'], updated['pid'])
        os.kill(first['pid'], 0)

    def test_old_bundle_and_updated_shortcut_each_reuse_their_helper(self):
        first = self.launch()
        self.helper.write_text(FAKE_HELPER + '\n# updated\n')
        updated = self.launch()
        self.helper.write_text(FAKE_HELPER)
        self.assertEqual(self.launch()['pid'], first['pid'])
        self.helper.write_text(FAKE_HELPER + '\n# updated\n')
        self.assertEqual(self.launch()['pid'], updated['pid'])

    def test_rejects_symlinked_state_and_log(self):
        self.support.mkdir()
        outside = self.root / 'outside'
        outside.write_text('private')
        (self.support / 'phone.json').symlink_to(outside)
        with self.assertRaisesRegex(ValueError, 'symlink'):
            self.launch()
        self.assertEqual(outside.read_text(), 'private')

    def test_failed_helper_returns_actionable_error(self):
        self.helper.write_text('raise SystemExit(2)\n')
        with self.assertRaisesRegex(RuntimeError, 'phone.*log|phone.*start'):
            self.launch()

    def test_invalid_port_is_rejected(self):
        with self.assertRaises(ValueError):
            module().ensure_phone(0, Path(sys.executable), self.helper, self.support)

    def test_health_never_follows_redirects_with_private_bearer(self):
        state = {'pid': os.getpid(), 'port': 19001, 'engine_port': 19002,
                 'nonce': 'a' * 32, 'version': 1, 'source_sha256': 'b' * 64}
        received = []
        class Destination(BaseHTTPRequestHandler):
            def log_message(self, *args): pass
            def do_GET(self):
                received.append(self.headers.get('Authorization'))
                body = json.dumps({'name': 'fright-feud-phone', **state}).encode()
                self.send_response(200)
                self.end_headers()
                self.wfile.write(body)
        target = ThreadingHTTPServer(('127.0.0.1', 0), Destination)
        class Redirect(BaseHTTPRequestHandler):
            def log_message(self, *args): pass
            def do_GET(self):
                self.send_response(302)
                self.send_header('Location', f'http://127.0.0.1:{target.server_port}/capture')
                self.end_headers()
        source = ThreadingHTTPServer(('127.0.0.1', 0), Redirect)
        for server in (target, source):
            threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            state['port'] = source.server_port
            self.assertFalse(module().healthy_phone(state, 19002, state['source_sha256']))
            self.assertEqual(received, [])
        finally:
            for server in (target, source):
                server.shutdown()
                server.server_close()


if __name__ == '__main__':
    unittest.main()
