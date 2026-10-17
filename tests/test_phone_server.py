"""Real HTTP checks for the LAN phone host's app-only transport boundary."""
import importlib.util
from pathlib import Path


def test_phone_server_exposes_constructor():
    path = Path(__file__).parents[1] / 'desktop/phone_server.py'
    assert path.exists(), 'paired phone transport has not been implemented'
    spec = importlib.util.spec_from_file_location('fright_feud_phone', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert callable(module.make_server)

import json
import os
from http.client import HTTPConnection
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread

import pytest

PATH = Path(__file__).parents[1] / 'desktop/phone_server.py'
SPEC = importlib.util.spec_from_file_location('fright_feud_phone', PATH)
phone = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(phone)
NONCE = 'board_nonce_12345678901234567890'


def snapshot():
    return {'version': 1, 'screen': 'setup', 'main': {
        'teams': [{'name': 'A', 'score': 0, 'strikes': 0}, {'name': 'B', 'score': 0, 'strikes': 0}],
        'r': 0, 'revealed': [], 'pot': 0, 'awarded': False, 'active': 0, 'buzz': None,
        'multOverride': {}, 'showQ': True}, 'bonus': {
        'rows': [[{'text': '', 'pts': 0, 'shown': False, 'ptsShown': False} for _ in range(5)] for _ in range(2)],
        'mask': False, 'left': 20, 'running': False},
        'rounds': [{'q': 'Question', 'a': [['Answer', 10]], 'mult': 1} for _ in range(8)],
        'questions': [{'q': 'Bonus question', 'a': [['Answer', 10]]} for _ in range(5)], 'soundOn': True}


@pytest.fixture
def servers():
    requests = []

    class Engine(BaseHTTPRequestHandler):
        def do_GET(self):
            requests.append((self.command, self.path, dict(self.headers)))
            if self.path.endswith('redirect'):
                self.send_response(302)
                self.send_header('Location', '/api/engine')
                self.end_headers()
                return
            body = b'{"name":"app-engine"}' if self.path == '/api/engine' else b'game asset'
            self.send_response(200)
            self.send_header('Content-Type', 'text/plain')
            self.send_header('Set-Cookie', 'engine-secret=never')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            if self.command != 'HEAD':
                self.wfile.write(body)

        do_HEAD = do_GET

        def log_message(self, *args):
            pass

    engine = ThreadingHTTPServer(('127.0.0.1', 0), Engine)
    proxy = phone.make_server(engine.server_port, nonce=NONCE)
    proxy.lan_addresses = ['192.168.1.9']
    proxy.address_source = lambda: proxy.lan_addresses
    proxy.clock = lambda: 100.
    for server in (engine, proxy):
        Thread(target=server.serve_forever, kwargs={'poll_interval': .01}, daemon=True).start()
    yield engine, proxy, requests
    for server in (proxy, engine):
        server.shutdown()
        server.server_close()


def request(proxy, path, method='GET', body=None, token=None, headers=None):
    connection = HTTPConnection('127.0.0.1', proxy.server_port, timeout=3)
    values = dict(headers or {})
    if token:
        values['Authorization'] = 'Bearer ' + token
    if isinstance(body, dict):
        body = json.dumps(body)
        values.setdefault('Content-Type', 'application/json')
    connection.request(method, path, body=body, headers=values)
    response = connection.getresponse()
    raw = response.read()
    result = (response.status, dict(response.headers), raw)
    connection.close()
    return result


def api(proxy, path, method='GET', body=None, token=NONCE, headers=None):
    status, headers, raw = request(proxy, path, method, body, token, headers)
    assert headers.get('Cache-Control') == 'no-store'
    assert headers.get('Content-Type') == 'application/json'
    assert 'Access-Control-Allow-Origin' not in headers
    return status, json.loads(raw)


def claim(proxy):
    status, value = api(proxy, '/phone/claim', 'POST', {})
    assert status == 200
    return value['lease']


def sync(proxy, lease, state=None, ack=None):
    return api(proxy, '/phone/sync', 'POST', {'lease': lease, 'state': state or snapshot(), 'ack': ack or []})


def host_token(proxy):
    status, value = api(proxy, '/phone/info')
    assert status == 200
    return value['host_token']


def test_reopening_pairing_refreshes_changed_wifi_addresses(servers):
    _, proxy, _ = servers
    proxy.address_source = lambda: ['192.168.2.14']
    status, info = api(proxy, '/phone/info')
    assert status == 200
    assert info['host_urls'][0].startswith(f'http://192.168.2.14:{proxy.server_port}/phone/#')
    assert request(proxy, '/phone/', headers={'Host': f'192.168.2.14:{proxy.server_port}'})[0] == 200
    assert request(proxy, '/phone/', headers={'Host': f'192.168.1.9:{proxy.server_port}'})[0] == 403


def command(proxy, token, identifier='command_1', action='question', args=None):
    body = {'id': identifier, 'action': action, 'args': args or {}}
    if action == 'bonusSet':
        body['generation'] = getattr(proxy, 'generation', 0)
    return api(proxy, '/phone/command', 'POST', body, token)


def test_clear_fences_late_bonus_save_even_before_board_acknowledges_reset(servers):
    _, proxy, _ = servers
    token, lease = host_token(proxy), claim(proxy)
    sync(proxy, lease)
    status, initial = api(proxy, '/phone/state', token=token)
    assert status == 200
    assert initial.get('generation') == 0
    stale = {'id': 'held-save', 'action': 'bonusSet',
             'args': {'p': 0, 'i': 0, 'text': 'Stale answer', 'pts': 45}, 'generation': 0}
    assert command(proxy, token, identifier='clear', action='bonusReset')[1]['generation'] == 1
    assert api(proxy, '/phone/command', 'POST', stale, token)[0] == 400
    commands = sync(proxy, lease)[1]['commands']
    assert [entry['action'] for entry in commands] == ['bonusReset']
    assert command(proxy, token, identifier='fresh-save', action='bonusSet',
                   args={'p': 0, 'i': 0, 'text': 'Fresh answer', 'pts': 2})[0] == 200


def test_start_and_clear_drop_queued_old_bonus_edits_and_missing_generation(servers):
    _, proxy, _ = servers
    token, lease = host_token(proxy), claim(proxy)
    sync(proxy, lease)
    args = {'p': 0, 'i': 0, 'text': 'Old answer', 'pts': 45}
    assert command(proxy, token, identifier='old-save', action='bonusSet', args=args)[0] == 200
    assert command(proxy, token, identifier='start', action='start', args={'names': ['A', 'B']})[0] == 200
    assert [entry['action'] for entry in sync(proxy, lease)[1]['commands']] == ['start']
    assert api(proxy, '/phone/command', 'POST', {'id': 'no-generation', 'action': 'bonusSet', 'args': args}, token)[0] == 400


def test_retrying_reset_id_does_not_advance_generation_twice(servers):
    _, proxy, _ = servers
    token, lease = host_token(proxy), claim(proxy)
    sync(proxy, lease)
    first = command(proxy, token, identifier='same-reset', action='bonusReset')
    repeated = command(proxy, token, identifier='same-reset', action='bonusReset')
    assert first[1].get('generation') == repeated[1].get('generation') == 1


def test_health_and_pairing_info_are_local_nonce_protected(servers):
    engine, proxy, upstream = servers
    assert api(proxy, '/phone/health', token=None)[0] == 403
    status, value = api(proxy, '/phone/health')
    assert status == 200
    assert value['name'] == 'fright-feud-phone'
    assert value['engine_port'] == engine.server_port
    assert value['nonce'] == NONCE and value['version'] == 1
    assert len(value['source_sha256']) == 64
    status, info = api(proxy, '/phone/info')
    assert info['host_urls'] == [f'http://192.168.1.9:{proxy.server_port}/phone/#{info["host_token"]}']
    assert info['host_connected'] is False
    proxy.lan_addresses = []
    assert api(proxy, '/phone/info')[1]['host_urls'] == []
    proxy.is_loopback = lambda peer: False
    assert api(proxy, '/phone/info')[0] == 403
    assert upstream == []


@pytest.mark.parametrize(('path', 'upstream_path'), [('/phone/', '/apps/fright-feud/assets/phone-host.html'),
    ('/phone/host.js', '/apps/fright-feud/assets/phone-host.js'),
    ('/phone/host.css', '/apps/fright-feud/assets/phone-host.css')])
def test_public_phone_assets_map_only_to_fixed_game_paths(servers, path, upstream_path):
    engine, proxy, upstream = servers
    proxy.is_loopback = lambda peer: False
    status, headers, body = request(proxy, path, headers={'Cookie': 'secret', 'Authorization': 'Bearer secret'})
    assert status == 200 and body == b'game asset'
    assert 'Set-Cookie' not in headers
    assert headers['Referrer-Policy'] == 'no-referrer'
    assert upstream[0][1] == upstream_path
    assert upstream[0][2]['Host'] == f'fright-feud.localhost:{engine.server_port}'
    assert 'Authorization' not in upstream[0][2] and 'Cookie' not in upstream[0][2]


@pytest.mark.parametrize('path', ['/', '/api/engine', '/apps/other/', '/apps/fright-feud/../secret',
    '/apps/fright-feud/%2e%2e/secret', '/apps/fright-feud/%252e%252e/secret',
    '/phone/host.js?token=secret', '/apps/fright-feud/index.html?engine=1',
    'http://evil.example/phone/', '//evil.example/phone/', '/phone/../api/engine', '/phone/other.js'])
def test_unsafe_paths_never_reach_upstream(servers, path):
    _, proxy, upstream = servers
    assert request(proxy, path)[0] in (400, 403, 404)
    assert upstream == []


def test_board_assets_require_loopback_peer(servers):
    _, proxy, upstream = servers
    assert request(proxy, '/apps/fright-feud/')[0] == 200
    proxy.is_loopback = lambda peer: False
    assert request(proxy, '/apps/fright-feud/', token=NONCE)[0] == 403
    assert len(upstream) == 1


def test_foreign_host_origin_and_duplicate_hosts_are_denied(servers):
    _, proxy, upstream = servers
    for headers in ({'Host': 'evil.example'}, {'Host': f'192.168.1.99:{proxy.server_port}'},
                    {'Origin': 'https://evil.example'}, {'Origin': 'null'},
                    {'Origin': f'http://127.0.0.1:{proxy.server_port + 1}'}):
        assert request(proxy, '/phone/', headers=headers)[0] == 403
    assert request(proxy, '/phone/', headers={'Host': f'192.168.1.9:{proxy.server_port}',
        'Origin': f'http://192.168.1.9:{proxy.server_port}'})[0] == 200
    connection = HTTPConnection('127.0.0.1', proxy.server_port)
    connection.putrequest('GET', '/phone/')
    connection.putheader('Host', 'evil.example')
    connection.endheaders()
    assert connection.getresponse().status == 403
    connection.close()
    assert len(upstream) == 1


def test_claim_sync_dedup_ack_and_refresh_recovery(servers):
    _, proxy, _ = servers
    token = host_token(proxy)
    assert command(proxy, token)[0] == 409
    lease = claim(proxy)
    assert sync(proxy, lease)[0] == 200
    assert command(proxy, token)[0] == 200
    assert command(proxy, token)[0] == 200
    status, value = sync(proxy, lease)
    assert value['commands'] == [{'id': 'command_1', 'action': 'question', 'args': {}}]
    assert sync(proxy, lease)[1]['commands'] == value['commands']
    assert sync(proxy, lease, ack=['command_1'])[1]['commands'] == []
    assert command(proxy, token)[0] == 200
    assert sync(proxy, lease)[1]['commands'] == []
    assert api(proxy, '/phone/state', token=token)[1] == {'state': snapshot(), 'board_connected': True, 'generation': 0, 'storage_warning': ''}
    status, replacement = api(proxy, '/phone/claim', 'POST', {})
    assert replacement['state'] == snapshot()
    assert replacement['lease'] != lease
    assert sync(proxy, lease)[0] == 409
    assert sync(proxy, replacement['lease'])[1]['commands'] == []


def test_heartbeats_and_command_expiry(servers):
    _, proxy, _ = servers
    token = host_token(proxy)
    lease = claim(proxy)
    sync(proxy, lease)
    assert command(proxy, token)[0] == 200
    assert api(proxy, '/phone/info')[1]['host_connected'] is True
    proxy.clock = lambda: 106.
    assert api(proxy, '/phone/info')[1]['host_connected'] is False
    assert api(proxy, '/phone/state', token=token)[1]['board_connected'] is False
    assert command(proxy, token, identifier='later')[0] == 409
    proxy.clock = lambda: 111.
    assert sync(proxy, lease)[1]['commands'] == []


@pytest.mark.parametrize(('action', 'args'), [('start', {'names': ['A', 'B']}), ('screen', {'screen': 'game'}),
    ('reveal', {'i': 0, 'round': 0}), ('revealRemaining', {'round': 0}), ('round', {'i': 1}),
    ('strike', {'team': 0}), ('unstrike', {'team': 1}), ('active', {'team': 0}),
    ('award', {'team': 1, 'round': 0}), ('score', {'team': 0, 'score': 123}), ('buzz', {'team': 1}),
    ('resetBuzz', {}), ('question', {}), ('multiplier', {}), ('sound', {}),
    ('bonusSet', {'p': 0, 'i': 4, 'text': '<private>', 'pts': 45}), ('bonusReveal', {'p': 0, 'i': 1}),
    ('bonusHide', {'p': 1, 'i': 2}), ('bonusRevealAll', {'p': 0}), ('timer', {'seconds': 25}),
    ('timerStop', {}), ('bonusMask', {}), ('bonusReset', {}), ('duplicateBuzz', {}), ('disconnect', {})])
def test_exact_allowlisted_actions_are_accepted(servers, action, args):
    _, proxy, _ = servers
    token = host_token(proxy)
    sync(proxy, claim(proxy))
    assert command(proxy, token, action=action, args=args)[0] == 200


@pytest.mark.parametrize(('action', 'args'), [('eval', {'code': 'alert(1)'}), ('question', {'url': 'file://secret'}),
    ('start', {'names': ['one']}), ('start', {'names': ['A' * 61, 'B']}), ('screen', {'screen': 'admin'}),
    ('reveal', {'i': 1, 'round': 0}), ('reveal', {'i': 0, 'round': 1}), ('award', {'team': 1, 'round': 1}),
    ('round', {'i': 8}), ('strike', {'team': True}), ('active', {'team': -1}),
    ('score', {'team': 0, 'score': 1.5}), ('score', {'team': 0, 'score': 1000000}),
    ('bonusSet', {'p': 0, 'i': 5, 'text': '', 'pts': 0}),
    ('bonusSet', {'p': 0, 'i': 0, 'text': 'x' * 201, 'pts': 0}),
    ('bonusSet', {'p': 0, 'i': 0, 'text': '', 'pts': -1}), ('timer', {'seconds': 21})])
def test_invalid_or_stale_actions_are_rejected(servers, action, args):
    _, proxy, _ = servers
    token = host_token(proxy)
    sync(proxy, claim(proxy))
    assert command(proxy, token, action=action, args=args)[0] == 400


def test_queue_payload_ids_and_snapshot_are_bounded(servers):
    _, proxy, _ = servers
    token = host_token(proxy)
    lease = claim(proxy)
    sync(proxy, lease)
    assert command(proxy, token, identifier='bad id')[0] == 400
    assert command(proxy, token, identifier='x' * 81)[0] == 400
    assert command(proxy, 'wrong')[0] == 403
    for index in range(64):
        assert command(proxy, token, identifier=str(index))[0] == 200
    assert command(proxy, token, identifier='overflow')[0] == 429
    invalid = snapshot()
    invalid['main']['teams'][0]['score'] = 'not a score'
    assert sync(proxy, lease, state=invalid)[0] == 400
    assert api(proxy, '/phone/sync', 'POST', {'lease': lease, 'state': [], 'ack': []})[0] == 400
    assert api(proxy, '/phone/claim', 'POST', {'unexpected': 1})[0] == 400
    assert api(proxy, '/phone/claim', 'POST', body='', headers={'Content-Length': '600000'})[0] == 413
    assert api(proxy, '/phone/claim', 'POST', body='not json')[0] == 400
    assert api(proxy, '/phone/claim', 'POST', body='{"a":NaN}')[0] == 400


def test_methods_and_redirects_do_not_escape(servers):
    _, proxy, upstream = servers
    assert request(proxy, '/phone/', method='POST', body='{}')[0] == 405
    assert request(proxy, '/phone/info', method='HEAD', token=NONCE)[0] == 405
    assert request(proxy, '/phone/', method='OPTIONS')[0] == 405
    assert request(proxy, '/apps/fright-feud/redirect', token=NONCE)[0] == 502
    status, headers, body = request(proxy, '/phone/host.js', method='HEAD')
    assert status == 200 and body == b'' and headers['Content-Length'] == '10'
    assert len(upstream) == 2


@pytest.mark.parametrize(('engine_port', 'listen_port', 'nonce'), [(80, 0, NONCE), (20000, 80, NONCE),
    (20000, 0, 'short'), (True, 0, NONCE), (20000, 0, 'x\n' * 20)])
def test_constructor_rejects_unsafe_ports_and_nonce(engine_port, listen_port, nonce):
    with pytest.raises(ValueError):
        phone.make_server(engine_port, listen_port, nonce)


def test_navigation_drops_queued_round_sensitive_commands(servers):
    _, proxy, _ = servers
    token = host_token(proxy)
    lease = claim(proxy)
    sync(proxy, lease)
    assert command(proxy, token, action='reveal', args={'i': 0, 'round': 0})[0] == 200
    state = snapshot()
    state['main']['r'] = 1
    assert sync(proxy, lease, state=state)[1]['commands'] == []


def test_acknowledged_disconnect_invalidates_phone_bearer(servers):
    _, proxy, _ = servers
    token = host_token(proxy)
    lease = claim(proxy)
    sync(proxy, lease)
    assert command(proxy, token, action='disconnect')[0] == 200
    assert sync(proxy, lease)[1]['commands'][0]['action'] == 'disconnect'
    assert sync(proxy, lease, ack=['command_1'])[1]['host_connected'] is False
    assert api(proxy, '/phone/state', token=token)[0] == 403
    assert host_token(proxy) != token


def test_cli_writes_private_versioned_identity_and_stops_with_engine(servers, tmp_path):
    import subprocess
    import sys
    import time
    engine, _, _ = servers
    state_file = tmp_path / 'phone-state.json'
    child = subprocess.Popen([sys.executable, str(PATH), '--engine-port', str(engine.server_port),
        '--nonce', NONCE, '--state-file', str(state_file)], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        for _ in range(100):
            if state_file.exists() or child.poll() is not None:
                break
            time.sleep(.03)
        assert state_file.exists(), child.communicate(timeout=1)
        value = json.loads(state_file.read_text())
        assert value['pid'] == child.pid and value['engine_port'] == engine.server_port
        assert value['version'] == 1 and value['nonce'] == NONCE
        assert len(value['source_sha256']) == 64
        assert os.stat(state_file).st_mode & 0o777 == 0o600
        engine.shutdown()
        engine.server_close()
        child.wait(timeout=20)
        assert child.returncode == 0
    finally:
        if child.poll() is None:
            child.terminate()
        child.communicate(timeout=3)


def test_malformed_bearers_leases_and_absolute_urls_fail_cleanly(servers):
    _, proxy, _ = servers
    assert api(proxy, '/phone/health', token='caf\u00e9')[0] == 403
    lease = claim(proxy)
    assert sync(proxy, '\u00e9' + lease)[0] == 409
    assert request(proxy, 'http://[broken/phone/', headers={'Host': f'127.0.0.1:{proxy.server_port}'})[0] == 400


def test_duplicate_json_keys_and_transfer_encoding_are_rejected(servers):
    _, proxy, _ = servers
    assert api(proxy, '/phone/claim', 'POST', '{"x":1,"x":2}')[0] == 400
    assert api(proxy, '/phone/claim', 'POST', '{}', headers={'Transfer-Encoding': 'chunked'})[0] == 400


def test_interface_discovery_uses_only_assigned_private_ipv4(monkeypatch):
    class Result:
        stdout = 'inet 127.0.0.1 netmask 0xff000000\ninet 192.168.5.9 netmask 0xffffff00\ninet 169.254.2.8\ninet 8.8.8.8\ninet 192.168.5.9\ninet 0.0.0.0\n'

    calls = []
    def run(command, **kwargs):
        calls.append(command)
        return Result()

    monkeypatch.setattr(phone.subprocess, 'run', run)
    assert phone.local_addresses() == ['169.254.2.8', '192.168.5.9']
    assert calls == [['/sbin/ifconfig']]


def test_interface_discovery_handles_missing_commands(monkeypatch):
    def unavailable(*args, **kwargs):
        raise FileNotFoundError('no interface utility')

    monkeypatch.setattr(phone.subprocess, 'run', unavailable)
    assert phone.local_addresses() == []


def test_json_lease_with_unpaired_surrogate_is_rejected(servers):
    _, proxy, _ = servers
    claim(proxy)
    assert sync(proxy, '\ud800')[0] == 409


@pytest.mark.parametrize('ack_time', [111., 171.])
def test_delivered_disconnect_late_ack_still_revokes_phone_bearer(servers, ack_time):
    _, proxy, _ = servers
    token = host_token(proxy)
    lease = claim(proxy)
    sync(proxy, lease)
    assert command(proxy, token, action='disconnect')[0] == 200
    assert sync(proxy, lease)[1]['commands'][0]['action'] == 'disconnect'
    proxy.clock = lambda: ack_time
    assert sync(proxy, lease, ack=['command_1'])[0] == 200
    assert api(proxy, '/phone/state', token=token)[0] == 403
    assert host_token(proxy) != token


def test_expired_undelivered_disconnect_ack_does_not_revoke_phone(servers):
    _, proxy, _ = servers
    token = host_token(proxy)
    lease = claim(proxy)
    sync(proxy, lease)
    assert command(proxy, token, action='disconnect')[0] == 200
    proxy.clock = lambda: 111.
    assert sync(proxy, lease, ack=['command_1'])[1]['commands'] == []
    assert api(proxy, '/phone/state', token=token)[0] == 200
    assert host_token(proxy) == token


def test_superseding_board_does_not_accept_previous_disconnect_delivery_ack(servers):
    _, proxy, _ = servers
    token = host_token(proxy)
    lease = claim(proxy)
    sync(proxy, lease)
    assert command(proxy, token, action='disconnect')[0] == 200
    assert sync(proxy, lease)[1]['commands'][0]['action'] == 'disconnect'
    replacement = claim(proxy)
    assert sync(proxy, replacement, ack=['command_1'])[0] == 200
    assert api(proxy, '/phone/state', token=token)[0] == 200


def test_unacknowledged_disconnect_deliveries_have_a_bounded_capacity(servers):
    _, proxy, _ = servers
    token = host_token(proxy)
    lease = claim(proxy)
    for index in range(64):
        proxy.clock = lambda index=index: 100. + index * 11
        sync(proxy, lease)
        assert command(proxy, token, identifier=f'disconnect_{index}', action='disconnect')[0] == 200
        assert sync(proxy, lease)[1]['commands'][0]['action'] == 'disconnect'
    proxy.clock = lambda: 1000.
    sync(proxy, lease)
    assert command(proxy, token, identifier='too_many', action='disconnect')[0] == 429
    assert command(proxy, token, identifier='ordinary', action='question')[0] == 200
    assert sync(proxy, lease, ack=['disconnect_0'])[0] == 200
    assert api(proxy, '/phone/state', token=token)[0] == 403


def series_snapshot():
    state = snapshot()
    state['version'] = 2
    state['series'] = {'game': 0, 'started': False, 'results': []}
    return state


def test_series_schema_and_stale_game_commands():
    state = series_snapshot()
    assert phone.valid_state(state)
    command = {'id': 'select-game-test', 'action': 'selectGame', 'args': {'game': 3}, 'game': 0}
    assert phone.valid_command(command, state)
    command['game'] = 1
    assert not phone.valid_command(command, state)
    command['game'] = 0
    command['args']['game'] = 4
    assert not phone.valid_command(command, state)
    state['series']['results'] = [{'game': 1, 't1': 'Owls', 't2': 'Ghouls', 's1': 123, 's2': 40, 'bonus': 200}]
    assert phone.valid_state(state)
    state['series']['results'] *= 2
    assert not phone.valid_state(state)


def test_series_results_survive_companion_restart(tmp_path):
    path = tmp_path / 'results.json'
    server = phone.make_server(8770, nonce=NONCE, results_path=path)
    try:
        result = [{'game': 1, 't1': 'Owls', 't2': 'Ghouls', 's1': 123, 's2': 40, 'bonus': 200}]
        server.save_results(result)
    finally:
        server.server_close()
    server = phone.make_server(8770, nonce=NONCE, results_path=path)
    try:
        assert server.results == result
        assert path.stat().st_mode & 0o777 == 0o600
    finally:
        server.server_close()


def test_result_write_failure_keeps_phone_transport_alive(servers, monkeypatch):
    _, proxy, _ = servers
    lease = claim(proxy)
    def fail(_): raise OSError('Disk full')
    monkeypatch.setattr(proxy, 'save_results', fail)
    status, value = sync(proxy, lease, series_snapshot())
    assert status == 200
    assert value['storage_warning']
    assert proxy.state['version'] == 2
    assert proxy.connected(proxy.board_seen)


def test_corrupt_results_do_not_prevent_hosting(tmp_path):
    path = tmp_path / 'results.json'
    path.write_text('broken json')
    server = phone.make_server(8770, nonce=NONCE, results_path=path)
    try:
        assert server.results is None
        assert server.storage_warning
        assert path.read_text() == 'broken json'
    finally:
        server.server_close()


def test_claim_keeps_in_memory_results_after_disk_failure(servers, monkeypatch):
    _, proxy, _ = servers
    proxy.results = []
    lease = claim(proxy)
    def fail(_): raise OSError('Disk full')
    monkeypatch.setattr(proxy, 'save_results', fail)
    state = series_snapshot()
    state['series']['results'] = [{'game': 1, 't1': 'Owls', 't2': 'Ghouls', 's1': 123, 's2': 40, 'bonus': 200}]
    assert sync(proxy, lease, state)[0] == 200
    status, value = api(proxy, '/phone/claim', 'POST', {})
    assert status == 200
    assert value['results'] == state['series']['results']
