#!/usr/bin/env python3
"""App-scoped, same-Wi-Fi transport for the private Fright Feud phone host.

Only fixed phone assets are public. The authoritative board and its nonce API
are loopback-only; engine administration and credentials are never forwarded.
"""
import argparse
from collections import OrderedDict
import hashlib
from http.client import HTTPConnection, HTTPException
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import ipaddress
import json
import os
from pathlib import Path
import re
import secrets
import subprocess
import tempfile
from threading import RLock, Thread
import time
from urllib.parse import unquote, urlsplit

PREFIX = '/apps/fright-feud/'
PUBLIC = {'/phone/': PREFIX + 'assets/phone-host.html',
          '/phone/host.js': PREFIX + 'assets/phone-host.js',
          '/phone/host.css': PREFIX + 'assets/phone-host.css'}
MAX_BODY = 256 * 1024
MAX_ASSET = 16 * 1024 * 1024
MAX_QUEUE = 64
MAX_IDS = 1024
ID = re.compile(r'[A-Za-z0-9_-]{1,80}')
SOURCE_SHA256 = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


def local_addresses():
    """Read assigned IPv4 interfaces without contacting an external service."""
    commands = (['/sbin/ifconfig'], ['ifconfig'], ['ip', '-o', '-4', 'addr', 'show'])
    for command in commands:
        try:
            result = subprocess.run(command, capture_output=True, text=True, timeout=3, check=True)
        except (OSError, subprocess.SubprocessError):
            continue
        addresses = []
        for candidate in re.findall(r'\binet\s+(\d+\.\d+\.\d+\.\d+)', result.stdout):
            try:
                address = ipaddress.IPv4Address(candidate)
            except ValueError:
                continue
            if (address.is_private or address.is_link_local) and not (address.is_loopback or address.is_unspecified or address.is_multicast):
                addresses.append(str(address))
        return sorted(set(addresses))
    return []


def loopback(peer):
    try:
        return ipaddress.ip_address(peer).is_loopback
    except ValueError:
        return False


def integer(value, low, high):
    return type(value) is int and low <= value <= high


def text(value, limit):
    return isinstance(value, str) and len(value) <= limit and not any(ord(c) < 32 for c in value)


def keys(value, expected):
    return isinstance(value, dict) and set(value) == set(expected.split())


def question_list(value, bonus=False):
    if not isinstance(value, list) or not 1 <= len(value) <= (5 if bonus else 64):
        return False
    for item in value:
        if not keys(item, 'q a' if bonus else 'q a mult') or not text(item['q'], 500):
            return False
        if not bonus and not integer(item['mult'], 1, 3):
            return False
        if not isinstance(item['a'], list) or not 1 <= len(item['a']) <= 8:
            return False
        for answer in item['a']:
            if not isinstance(answer, list) or len(answer) != 2 or not text(answer[0], 200) or not integer(answer[1], 0, 999):
                return False
    return True


def valid_results(value):
    if not isinstance(value, list) or len(value) > 4:
        return False
    games = set()
    for result in value:
        if not keys(result, 'game t1 t2 s1 s2 bonus') or not integer(result['game'], 1, 4) or result['game'] in games:
            return False
        if not all(text(result[name], 60) for name in ('t1', 't2')) or not all(integer(result[name], -999999, 999999) for name in ('s1', 's2')) or not integer(result['bonus'], 0, 9990):
            return False
        games.add(result['game'])
    return True


def valid_state(state):
    if not isinstance(state, dict):
        return False
    expected = 'version screen main bonus rounds questions soundOn'
    if state.get('version') == 2:
        expected += ' series'
        series = state.get('series')
        if not keys(series, 'game started results') or not integer(series['game'], 0, 3) or type(series['started']) is not bool or not valid_results(series['results']):
            return False
    if not keys(state, expected):
        return False
    if type(state['version']) is not int or state['version'] not in (1, 2) or state['screen'] not in ('setup', 'game', 'bonus') or type(state['soundOn']) is not bool:
        return False
    if not question_list(state['rounds']) or not question_list(state['questions'], bonus=True):
        return False
    main, bonus = state['main'], state['bonus']
    if not keys(main, 'teams r revealed pot awarded active buzz multOverride showQ'):
        return False
    teams = main['teams']
    if not isinstance(teams, list) or len(teams) != 2:
        return False
    for team in teams:
        if not keys(team, 'name score strikes') or not text(team['name'], 60) or not integer(team['score'], -999999, 999999) or not integer(team['strikes'], 0, 3):
            return False
    if not integer(main['r'], 0, len(state['rounds']) - 1) or not integer(main['pot'], 0, 999999):
        return False
    if any(type(main[name]) is not bool for name in ('awarded', 'showQ')):
        return False
    if any(main[name] is not None and not integer(main[name], 0, 1) for name in ('active', 'buzz')):
        return False
    revealed = main['revealed']
    if not isinstance(revealed, list) or len(revealed) > 8 or any(not integer(i, 0, len(state['rounds'][main['r']]['a']) - 1) for i in revealed) or len(set(revealed)) != len(revealed):
        return False
    overrides = main['multOverride']
    if not isinstance(overrides, dict) or len(overrides) > len(state['rounds']):
        return False
    if any(not re.fullmatch(r'0|[1-9][0-9]?', key) or int(key) >= len(state['rounds']) or not integer(value, 1, 3) for key, value in overrides.items()):
        return False
    if not keys(bonus, 'rows mask left running') or any(type(bonus[name]) is not bool for name in ('mask', 'running')) or not integer(bonus['left'], 0, 25):
        return False
    rows = bonus['rows']
    if not isinstance(rows, list) or len(rows) != 2:
        return False
    for player in rows:
        if not isinstance(player, list) or len(player) != len(state['questions']):
            return False
        for row in player:
            if not keys(row, 'text pts shown ptsShown') or not text(row['text'], 200) or not integer(row['pts'], 0, 999) or any(type(row[name]) is not bool for name in ('shown', 'ptsShown')):
                return False
    return True


def valid_command(value, state):
    if not isinstance(value, dict):
        return False
    expected = 'id action args'
    if 'generation' in value:
        expected += ' generation'
    if 'game' in value:
        expected += ' game'
    shape = keys(value, expected)
    if state and state.get('version') == 2:
        if not integer(value.get('game'), 0, 3) or value['game'] != state['series']['game']:
            return False
    elif 'game' in value:
        return False
    if (not shape or not isinstance(value['id'], str) or ID.fullmatch(value['id']) is None
            or ('generation' in value and not integer(value['generation'], 0, 2 ** 53 - 1))):
        return False
    action, args = value['action'], value['args']
    if not isinstance(action, str) or not isinstance(args, dict):
        return False
    if action in ('selectGame', 'finishGame', 'clearResults'):
        if not state or state.get('version') != 2:
            return False
        if action == 'selectGame':
            return state['screen'] == 'setup' and keys(args, 'game') and integer(args['game'], 0, 3)
        return not args and (state['series']['started'] if action == 'finishGame' else state['screen'] == 'setup')
    empty = {'resetBuzz', 'question', 'multiplier', 'sound', 'timerStop', 'bonusMask', 'bonusReset', 'duplicateBuzz', 'disconnect'}
    if action in empty:
        return not args
    if action == 'start':
        return keys(args, 'names') and isinstance(args['names'], list) and len(args['names']) == 2 and all(text(name, 60) for name in args['names'])
    if action == 'screen':
        return keys(args, 'screen') and args['screen'] in ('setup', 'game', 'bonus')
    if action in ('strike', 'unstrike', 'active', 'buzz'):
        return keys(args, 'team') and integer(args['team'], 0, 1)
    if action == 'score':
        return keys(args, 'team score') and integer(args['team'], 0, 1) and integer(args['score'], -999999, 999999)
    if action == 'timer':
        return keys(args, 'seconds') and type(args['seconds']) is int and args['seconds'] in (20, 25)
    if not state:
        return False
    if action == 'round':
        return keys(args, 'i') and integer(args['i'], 0, len(state['rounds']) - 1)
    if action in ('reveal', 'revealRemaining', 'award'):
        expected = {'reveal': 'i round', 'revealRemaining': 'round', 'award': 'team round'}[action]
        if not keys(args, expected) or not integer(args['round'], 0, len(state['rounds']) - 1) or args['round'] != state['main']['r']:
            return False
        if action == 'reveal':
            return integer(args['i'], 0, len(state['rounds'][args['round']]['a']) - 1)
        return action != 'award' or integer(args['team'], 0, 1)
    if action == 'bonusRevealAll':
        return keys(args, 'p') and integer(args['p'], 0, 1)
    if action in ('bonusSet', 'bonusReveal', 'bonusHide'):
        expected = 'p i text pts' if action == 'bonusSet' else 'p i'
        if not keys(args, expected) or not integer(args['p'], 0, 1) or not integer(args['i'], 0, len(state['questions']) - 1):
            return False
        return action != 'bonusSet' or (text(args['text'], 200) and integer(args['pts'], 0, 999))
    return False


class PhoneServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, engine_port, listen_port, nonce, results_path=None):
        self.results_path = results_path
        self.results = None
        self.storage_warning = ''
        if results_path is not None:
            try:
                if results_path.is_symlink():
                    raise ValueError('Refusing symlink results file')
                saved = json.loads(results_path.read_text()) if results_path.exists() else []
                if not valid_results(saved):
                    raise ValueError('Invalid saved game results')
                self.results = saved
            except (OSError, ValueError):
                # Preserve unreadable data for recovery; browser storage remains usable.
                self.results_path = None
                self.storage_warning = 'Saved results could not be read. Results will use browser storage for this session.'
        self.engine_port, self.nonce = engine_port, nonce
        self.host_token = secrets.token_urlsafe(32)
        self.lease = None
        self.state = None
        self.board_seen = None
        self.host_seen = None
        self.generation = 0
        self.pending = OrderedDict()
        # Delivery acknowledgements can arrive after the ten-second send queue
        # expires. Retain at most MAX_QUEUE disconnect IDs for the board lease.
        self.delivered_disconnects = set()
        self.seen = OrderedDict()
        self.lock = RLock()
        self.clock = time.monotonic
        self.is_loopback = loopback
        self.address_source = local_addresses
        self.lan_addresses = self.address_source()
        super().__init__(('0.0.0.0', listen_port), PhoneHandler)

    def save_results(self, results):
        if not valid_results(results):
            raise ValueError('Invalid game results')
        if results == self.results:
            return
        if self.results_path is not None:
            if self.results_path.is_symlink():
                raise ValueError('Refusing symlink results file')
            self.results_path.parent.mkdir(parents=True, exist_ok=True)
            descriptor, temporary = tempfile.mkstemp(prefix='.results-', dir=self.results_path.parent)
            try:
                with os.fdopen(descriptor, 'w') as target:
                    json.dump(results, target)
                os.replace(temporary, self.results_path)
            finally:
                if os.path.exists(temporary):
                    os.unlink(temporary)
        self.results = results

    def connected(self, heartbeat):
        return heartbeat is not None and self.clock() - heartbeat <= 5

    def prune(self):
        now = self.clock()
        self.pending = OrderedDict((key, item) for key, item in self.pending.items() if now - item[1] <= 10)
        self.seen = OrderedDict((key, item) for key, item in self.seen.items() if now - item <= 60)


class PhoneHandler(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.0'

    def log_message(self, *args):
        pass  # Never put private fragments, headers or request bodies in logs.

    def json(self, status, value):
        body = json.dumps(value, separators=(',', ':'), allow_nan=False).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        if self.command != 'HEAD':
            self.wfile.write(body)

    def reject(self, status, message):
        self.json(status, {'error': message})

    def do_GET(self):
        self.dispatch()

    do_HEAD = do_GET
    do_POST = do_GET
    do_OPTIONS = do_GET
    do_PUT = do_GET
    do_DELETE = do_GET
    do_PATCH = do_GET

    def dispatch(self):
        server = self.server
        hosts = self.headers.get_all('Host', [])
        allowed = {'127.0.0.1', 'localhost', *server.lan_addresses}
        if len(hosts) != 1 or hosts[0] not in {f'{host}:{server.server_port}' for host in allowed}:
            return self.reject(403, 'Unrecognized local Host')
        origins = self.headers.get_all('Origin', [])
        if origins and (len(origins) != 1 or origins[0] != 'http://' + hosts[0]):
            return self.reject(403, 'Foreign Origin')
        try:
            parsed = urlsplit(self.path)
        except ValueError:
            return self.reject(400, 'Malformed local path')
        decoded = unquote(parsed.path)
        if (parsed.scheme or parsed.netloc or parsed.query or parsed.fragment or not self.path.startswith('/') or '%' in decoded or '\\' in decoded or '..' in decoded.split('/') or any(ord(char) < 32 for char in decoded)):
            return self.reject(400, 'Only fixed local paths are accepted')
        path = parsed.path
        if path in PUBLIC or path.startswith(PREFIX):
            if self.command not in ('GET', 'HEAD'):
                return self.reject(405, 'Method not allowed')
            if path not in PUBLIC and not server.is_loopback(self.client_address[0]):
                return self.reject(403, 'Board assets require loopback')
            return self.asset(PUBLIC.get(path, path))
        board_routes = {'/phone/health': 'GET', '/phone/info': 'GET', '/phone/claim': 'POST', '/phone/sync': 'POST'}
        phone_routes = {'/phone/state': 'GET', '/phone/command': 'POST'}
        if path not in board_routes and path not in phone_routes:
            return self.reject(404, 'Unknown route')
        board = path in board_routes
        if board and not server.is_loopback(self.client_address[0]):
            return self.reject(403, 'Board API requires loopback')
        auth = self.headers.get_all('Authorization', [])
        with server.lock:
            token = server.nonce if board else server.host_token
            if len(auth) != 1 or not secrets.compare_digest(auth[0].encode('utf-8'), ('Bearer ' + token).encode('utf-8')):
                return self.reject(403, 'Invalid bearer')
            if self.command != (board_routes if board else phone_routes)[path]:
                return self.reject(405, 'Method not allowed')
            body = None
            if self.command == 'POST':
                body = self.read_body()
                if body is None:
                    return
            server.prune()
            self.api(path, body)

    def read_body(self):
        lengths = self.headers.get_all('Content-Length', [])
        if self.headers.get('Transfer-Encoding') or len(lengths) != 1 or not re.fullmatch(r'[0-9]{1,10}', lengths[0]):
            self.reject(400, 'A bounded Content-Length is required')
            return None
        length = int(lengths[0])
        if length > MAX_BODY:
            self.reject(413, 'Payload too large')
            return None
        self.connection.settimeout(3)
        try:
            raw = self.rfile.read(length)
            if len(raw) != length:
                raise ValueError('Truncated body')
            value = json.loads(raw, parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))
            if not isinstance(value, dict):
                raise ValueError('Object required')
            return value
        except (ValueError, OSError, RecursionError):
            self.reject(400, 'A JSON object is required')
            return None

    def api(self, path, body):
        server = self.server
        now = server.clock()
        if path == '/phone/health':
            return self.json(200, {'name': 'fright-feud-phone', 'engine_port': server.engine_port,
                'nonce': server.nonce, 'version': 1, 'source_sha256': SOURCE_SHA256})
        if path == '/phone/info':
            # A durable service may outlive a Wi-Fi/DHCP change. Refresh on the
            # local pairing action, never on unauthenticated network requests.
            server.lan_addresses = server.address_source()
            return self.json(200, {'host_urls': [f'http://{host}:{server.server_port}/phone/#{server.host_token}' for host in server.lan_addresses],
                'host_token': server.host_token, 'host_connected': server.connected(server.host_seen), 'storage_warning': server.storage_warning})
        if path == '/phone/claim':
            if body:
                return self.reject(400, 'Claim requires an empty object')
            server.lease = secrets.token_urlsafe(24)
            server.board_seen = None
            server.pending.clear()
            server.delivered_disconnects.clear()
            return self.json(200, {'lease': server.lease, 'state': server.state, 'results': server.state['series']['results'] if server.state and server.state.get('version') == 2 else server.results, 'storage_warning': server.storage_warning})
        if path == '/phone/sync':
            if not keys(body, 'lease state ack') or not isinstance(body['lease'], str):
                return self.reject(400, 'Invalid sync')
            if not server.lease or not body['lease'].isascii() or not secrets.compare_digest(body['lease'], server.lease):
                return self.reject(409, 'Board lease replaced')
            if not valid_state(body['state']) or not isinstance(body['ack'], list) or len(body['ack']) > MAX_QUEUE or any(not isinstance(i, str) or ID.fullmatch(i) is None for i in body['ack']):
                return self.reject(400, 'Invalid snapshot or acknowledgements')
            disconnect = any(i in server.delivered_disconnects for i in body['ack'])
            for identifier in body['ack']:
                server.pending.pop(identifier, None)
                server.delivered_disconnects.discard(identifier)
            if disconnect:
                server.host_token = secrets.token_urlsafe(32)
                server.host_seen = None
                server.pending.clear()
                server.delivered_disconnects.clear()
                server.seen.clear()
            if body['state'].get('version') == 2:
                try:
                    server.save_results(body['state']['series']['results'])
                    if server.results_path is not None:
                        server.storage_warning = ''
                except (OSError, ValueError):
                    server.storage_warning = 'Results could not be saved to disk. Keep the board open; saving will retry.'
            server.state = body['state']
            server.board_seen = now
            server.pending = OrderedDict((key, item) for key, item in server.pending.items()
                if valid_command(item[0], server.state)
                and (item[0]['action'] != 'bonusSet' or item[0].get('generation') == server.generation))
            server.delivered_disconnects.update(key for key, item in server.pending.items() if item[0]['action'] == 'disconnect')
            return self.json(200, {'commands': [item[0] for item in server.pending.values()], 'host_connected': server.connected(server.host_seen), 'storage_warning': server.storage_warning})
        if path == '/phone/state':
            server.host_seen = now
            return self.json(200, {'state': server.state, 'board_connected': server.connected(server.board_seen),
                'generation': server.generation, 'storage_warning': server.storage_warning})
        if not valid_command(body, server.state):
            return self.reject(400, 'Invalid or stale action')
        if body['action'] == 'bonusSet' and body.get('generation') != server.generation:
            return self.reject(400, 'Bonus input belongs to an earlier board')
        if not server.connected(server.board_seen):
            return self.reject(409, 'Board disconnected')
        server.host_seen = now
        identifier = body['id']
        if identifier in server.seen or identifier in server.delivered_disconnects:
            return self.json(200, {'accepted': True, 'generation': server.generation})
        if body['action'] == 'disconnect':
            outstanding = server.delivered_disconnects | {key for key, item in server.pending.items() if item[0]['action'] == 'disconnect'}
            if len(outstanding) >= MAX_QUEUE:
                return self.reject(429, 'Disconnect acknowledgement capacity is full')
        if len(server.pending) >= MAX_QUEUE or len(server.seen) >= MAX_IDS:
            return self.reject(429, 'Command queue is full')
        if body['action'] in ('bonusReset', 'start', 'selectGame', 'finishGame'):
            # Fence delayed edits before the board consumes the clear command.
            server.generation += 1
        server.pending[identifier] = (body, now)
        server.seen[identifier] = now
        return self.json(200, {'accepted': True, 'generation': server.generation})

    def asset(self, path):
        connection = HTTPConnection('127.0.0.1', self.server.engine_port, timeout=8)
        try:
            connection.request(self.command, path, headers={
                'Host': f'fright-feud.localhost:{self.server.engine_port}', 'Accept-Encoding': 'identity'})
            response = connection.getresponse()
            if 300 <= response.status < 400:
                raise ValueError('Redirect denied')
            declared = response.getheader('Content-Length')
            if declared is not None and not 0 <= int(declared) <= MAX_ASSET:
                raise ValueError('Asset too large')
            body = b'' if self.command == 'HEAD' else response.read(MAX_ASSET + 1)
            if len(body) > MAX_ASSET:
                raise ValueError('Asset too large')
            self.send_response(response.status)
            for name in ('Content-Type', 'Content-Language', 'Content-Security-Policy', 'ETag', 'Last-Modified'):
                value = response.getheader(name)
                if value is not None:
                    self.send_header(name, value)
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Referrer-Policy', 'no-referrer')
            self.send_header('Content-Length', declared if self.command == 'HEAD' and declared else str(len(body)))
            self.end_headers()
            if self.command != 'HEAD':
                self.wfile.write(body)
        except (OSError, ValueError, HTTPException):
            self.reject(502, 'The local App Engine is unavailable')
        finally:
            connection.close()


def make_server(engine_port, listen_port=0, nonce='', results_path=None):
    if not integer(engine_port, 1024, 65535) or not (type(listen_port) is int and (listen_port == 0 or 1024 <= listen_port <= 65535)):
        raise ValueError('Invalid local port')
    if not isinstance(nonce, str) or not re.fullmatch(r'[A-Za-z0-9_-]{20,128}', nonce):
        raise ValueError('Invalid board nonce')
    return PhoneServer(engine_port, listen_port, nonce, results_path)


def watch_engine(server):
    failures = 0
    while failures < 3:
        time.sleep(3)
        connection = HTTPConnection('127.0.0.1', server.engine_port, timeout=2)
        try:
            connection.request('GET', '/api/engine')
            response = connection.getresponse()
            value = json.loads(response.read(65536))
            failures = 0 if response.status == 200 and isinstance(value, dict) and value.get('name') == 'app-engine' else failures + 1
        except (OSError, ValueError, HTTPException):
            failures += 1
        finally:
            connection.close()
    server.shutdown()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--engine-port', type=int, required=True)
    parser.add_argument('--listen-port', type=int, default=0)
    parser.add_argument('--state-file', type=Path, required=True)
    parser.add_argument('--nonce', required=True)
    args = parser.parse_args()
    server = make_server(args.engine_port, args.listen_port, args.nonce, args.state_file.parent / "game-results.json")
    args.state_file.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix='.phone-', dir=args.state_file.parent)
    try:
        with os.fdopen(descriptor, 'w') as target:
            json.dump({'pid': os.getpid(), 'port': server.server_port, 'engine_port': args.engine_port,
                'nonce': args.nonce, 'version': 1, 'source_sha256': SOURCE_SHA256}, target)
        os.replace(temporary, args.state_file)
        Thread(target=watch_engine, args=(server,), daemon=True).start()
        server.serve_forever(poll_interval=.2)
    finally:
        server.server_close()
        if os.path.exists(temporary):
            os.unlink(temporary)


if __name__ == '__main__':
    main()
