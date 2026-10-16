"""Start/reuse a durable phone companion without altering the signed Mac app."""
import fcntl
import hashlib
from http.client import HTTPConnection, HTTPException
import json
import os
from pathlib import Path
import re
import secrets
import subprocess
import tempfile
import time
from urllib.request import Request, build_opener, ProxyHandler, HTTPRedirectHandler


class LocalOnly(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, newurl):
        return None


def phone_supported(engine_port):
    """Check the engine's actual installed game before offering a paired board."""
    connection = HTTPConnection('127.0.0.1', engine_port, timeout=3)
    try:
        for relative, expected in (('', 'html'), ('assets/phone-board.js', 'javascript'),
                                   ('assets/phone-host.html', 'html')):
            connection.request('GET', '/apps/fright-feud/' + relative, headers={
                'Host': f'fright-feud.localhost:{engine_port}', 'Accept-Encoding': 'identity'})
            response = connection.getresponse()
            body = response.read(256 * 1024 + 1)
            if (response.status != 200 or expected not in response.getheader('Content-Type', '')
                    or len(body) > 256 * 1024):
                return False
            if not relative and b'assets/phone-board.js' not in body:
                return False
        return True
    except (OSError, ValueError, HTTPException):
        return False
    finally:
        connection.close()


def _read(path):
    try:
        value = json.loads(path.read_text())
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def healthy_phone(state, engine_port, digest):
    port, nonce = state.get('port'), state.get('nonce')
    if (type(port) is not int or not 1024 <= port <= 65535
            or state.get('engine_port') != engine_port
            or type(state.get('pid')) is not int or state['pid'] <= 0
            or state.get('source_sha256') != digest or state.get('version') != 1
            or not isinstance(nonce, str) or not re.fullmatch(r'[A-Za-z0-9_-]{20,128}', nonce)):
        return False
    try:
        request = Request(f'http://127.0.0.1:{port}/phone/health', headers={'Authorization': 'Bearer ' + nonce})
        with build_opener(ProxyHandler({}), LocalOnly()).open(request, timeout=1) as response:
            value = json.loads(response.read(65536))
        return (value.get('name') == 'fright-feud-phone' and value.get('nonce') == nonce
                and value.get('engine_port') == engine_port and value.get('version') == 1
                and value.get('source_sha256') == digest)
    except (OSError, ValueError, AttributeError):
        return False


def _result(state):
    return {'url': f"http://127.0.0.1:{state['port']}/apps/fright-feud/#ff_board={state['nonce']}",
            'port': state['port'], 'pid': state['pid']}


def _private_file(path):
    if path.is_symlink():
        raise ValueError(f'Refusing symlink: {path}')


def ensure_phone(engine_port, python, helper, support, timeout=12):
    """Return {url,port,pid}; never stop an existing process or change engine roots."""
    if type(engine_port) is not int or not 1024 <= engine_port <= 65535:
        raise ValueError('Invalid engine port')
    python, helper, support = Path(python), Path(helper), Path(support)
    if support.is_symlink():
        raise ValueError(f'Refusing symlink support directory: {support}')
    support.mkdir(parents=True, exist_ok=True)
    latest_path, log_path, lock_path = [support / name for name in ('phone.json', 'phone.log', 'phone.lock')]
    for path in (latest_path, log_path, lock_path):
        _private_file(path)
    with lock_path.open('a') as lock:
        os.chmod(lock_path, 0o600)
        fcntl.flock(lock, fcntl.LOCK_EX)
        source = helper.read_bytes()
        digest = hashlib.sha256(source).hexdigest()
        # A Desktop source update and an older installed signed bundle can coexist.
        # Each reuses its own authenticated helper instead of starting one per click.
        state_path = support / f'phone-{digest}.json'
        _private_file(state_path)
        previous = _read(state_path)
        if healthy_phone(previous, engine_port, digest):
            return _result(previous)
        durable = support / 'phone-service' / digest
        if durable.parent.is_symlink() or durable.is_symlink():
            raise ValueError(f'Refusing symlink helper directory: {durable}')
        durable.mkdir(parents=True, exist_ok=True)
        target = durable / 'phone_server.py'
        _private_file(target)
        if not target.exists() or target.read_bytes() != source:
            fd, temporary = tempfile.mkstemp(prefix='.phone-', dir=durable)
            try:
                with os.fdopen(fd, 'wb') as stream:
                    stream.write(source)
                os.replace(temporary, target)
            finally:
                if os.path.exists(temporary):
                    os.unlink(temporary)
        nonce = secrets.token_urlsafe(32)
        environment = {key: value for key, value in os.environ.items() if not key.startswith('PYTHON')}
        with log_path.open('ab', buffering=0) as log:
            os.chmod(log_path, 0o600)
            process = subprocess.Popen([str(python), '-I', '-B', str(target), '--engine-port', str(engine_port),
                                        '--listen-port', '0', '--state-file', str(state_path), '--nonce=' + nonce],
                                       cwd=durable, env=environment, stdin=subprocess.DEVNULL,
                                       stdout=log, stderr=log, start_new_session=True, close_fds=True)
        deadline = time.monotonic() + min(timeout, 15)
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise RuntimeError(f'The phone service could not start. See the phone log: {log_path}')
            state = _read(state_path)
            if state.get('nonce') == nonce and state.get('pid') == process.pid:
                os.chmod(state_path, 0o600)
                if healthy_phone(state, engine_port, digest):
                    fd, temporary = tempfile.mkstemp(prefix='.phone-state-', dir=support)
                    with os.fdopen(fd, 'w') as stream:
                        json.dump(state, stream)
                    os.replace(temporary, latest_path)
                    return _result(state)
            time.sleep(.1)
        raise RuntimeError(f'The phone connection timed out. See the phone log: {log_path}')
