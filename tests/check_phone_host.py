"""Paired browser regressions. --engine-url uses a disposable real App Engine."""
import argparse
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import importlib.util
import json
from pathlib import Path
from threading import Thread
from urllib.parse import urlsplit
from urllib.request import Request, urlopen
from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('phone_server', ROOT / 'desktop/phone_server.py')
phone_server = importlib.util.module_from_spec(spec)
spec.loader.exec_module(phone_server)

class EngineFixture(SimpleHTTPRequestHandler):
    """Match the engine's fixed app asset prefix rather than serving repo at /."""
    def translate_path(self, path):
        path = urlsplit(path).path
        if not path.startswith('/apps/fright-feud/'):
            return str(ROOT / '__not_found__')
        return super().translate_path('/' + path[len('/apps/fright-feud/'):])
    def log_message(self, *args):
        pass

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--engine-url')
    parser.add_argument('--url', help='existing companion board URL including nonce fragment')
    parser.add_argument('--screenshots', type=Path)
    args = parser.parse_args()
    fixture = companion = None
    if args.url:
        board_url = args.url
        nonce = urlsplit(board_url).fragment.removeprefix('ff_board=')
        origin = board_url.split('/apps/')[0]
    else:
        if args.engine_url:
            engine_port = urlsplit(args.engine_url).port
        else:
            fixture = ThreadingHTTPServer(('127.0.0.1', 0), partial(EngineFixture, directory=str(ROOT)))
            Thread(target=fixture.serve_forever, daemon=True).start()
            engine_port = fixture.server_port
        nonce = 'phone-browser-test-nonce'
        companion = phone_server.make_server(engine_port, nonce=nonce)
        Thread(target=companion.serve_forever, daemon=True).start()
        origin = f'http://127.0.0.1:{companion.server_port}'
        board_url = origin + '/apps/fright-feud/#ff_board=' + nonce
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            board = browser.new_context(viewport={'width': 1440, 'height': 1000}).new_page()
            board.goto(board_url)
            board.locator('#splash').click()
            expect(board.get_by_role('button', name='Connect phone', exact=True)).to_be_visible(timeout=4000)
            def board_wait(expression):
                board.wait_for_function(expression)
            def post(identifier, action, payload):
                return phone.request.post(origin + '/phone/command', headers={'Authorization': 'Bearer ' + host_token}, data={'id':identifier, 'action':action, 'args':payload})
            def shot(page, name):
                if args.screenshots:
                    args.screenshots.mkdir(parents=True, exist_ok=True)
                    if page.locator('#splash').count():
                        page.wait_for_function("getComputedStyle(document.getElementById('splash')).opacity === '0'")
                        expect(page.locator('#xover')).to_be_hidden()
                    page.screenshot(path=str(args.screenshots / name), full_page=not name.startswith('phone-'))
            board.get_by_role('button', name='Connect phone', exact=True).click()
            expect(board.locator('#phonePair')).to_be_visible()
            board.wait_for_function("AC && AC.state === 'running'")
            info = json.load(urlopen(Request(origin + '/phone/info', headers={'Authorization': 'Bearer ' + nonce})))
            host_token = info['host_token']
            phone_context = browser.new_context(viewport={'width':390, 'height':844}, is_mobile=True, has_touch=True)
            phone = phone_context.new_page()
            phone.goto(origin + '/phone/#' + host_token)
            expect(phone.locator('#connection')).to_contain_text('Connected')
            expect(board.locator('#phonePair')).to_be_hidden()
            expect(board.locator('#startBtn')).to_be_hidden()
            phone.locator('#teamName0').fill('Night Owls')
            phone.locator('#teamName1').fill('Pumpkin Kings')
            phone.locator('#start').click()
            expect(phone.locator('#name0')).to_have_text('Night Owls')
            board_wait("S.teams[0].name === 'Night Owls'")
            phone.locator('#reveal0').click()
            board_wait('S.revealed.has(0) && S.pot === 28')
            assert board.evaluate('AC.state') == 'running'
            expect(board.locator('#board .tile').first).to_have_class('tile flipped')
            # Both transport deduplication and existing award guard prevent double scoring.
            assert post('double-award', 'award', {'team':0,'round':0}).ok
            assert post('double-award', 'award', {'team':0,'round':0}).ok
            board_wait('S.teams[0].score === 28 && S.awarded')
            assert post('award-again', 'award', {'team':0,'round':0}).ok
            board.wait_for_timeout(750)
            assert board.evaluate('S.teams[0].score') == 28
            phone.locator('[data-action="strike"]').first.click()
            board_wait('S.teams[0].strikes === 1')
            phone.locator('[data-action="unstrike"]').first.click()
            board_wait('S.teams[0].strikes === 0')
            phone.locator('[data-action="active"]').nth(1).click()
            board_wait('S.active === 1')
            phone.locator('[data-action="buzz"]').first.click()
            board_wait('S.buzz === 0')
            phone.locator('[data-action="resetBuzz"]').click()
            board_wait('S.buzz === null')
            phone.locator('#scoreInput1').fill('100')
            phone.locator('[data-score="1"]').click()
            board_wait('S.teams[1].score === 100')
            phone.locator('#multiplier').click()
            board_wait('mult() === 2')
            phone.locator('#question').click()
            board_wait('!S.showQ')
            phone.locator('#question').click()
            board_wait('S.showQ')
            phone.locator('#sound').click()
            board_wait('!soundOn')
            phone.locator('#sound').click()
            board_wait('soundOn')
            shot(phone, 'phone-main.png')
            shot(board, 'board-main.png')
            phone.get_by_role('button', name='Next round', exact=True).click()
            board_wait('S.r === 1')
            board.wait_for_timeout(500)
            assert post('stale-round', 'reveal', {'i':0,'round':0}).status == 400
            # Both are valid against the queued snapshot; adapter rejects the old round after navigation.
            board.route('**/phone/sync', lambda route: route.abort())
            board.wait_for_timeout(500)
            assert post('queued-round', 'round', {'i':2}).ok
            assert post('queued-stale', 'reveal', {'i':0,'round':1}).ok
            board.unroute('**/phone/sync')
            board_wait('S.r === 2')
            assert board.evaluate('S.revealed.size') == 0
            phone.get_by_role('button', name='Bonus round', exact=True).click()
            expect(phone.locator('#text0_0')).to_be_visible()
            phone.locator('#text0_0').fill('Orange')
            phone.wait_for_timeout(1200)
            expect(phone.locator('#text0_0')).to_be_focused()
            expect(phone.locator('#text0_0')).to_have_value('Orange')
            board_wait("FM.rows[0][0].text === 'Orange' && FM.rows[0][0].pts === 45")
            assert board.locator('#fmcol0 .fmrow .a').first.inner_text() == ''
            assert board.locator('#fmcol0 .fmrow .p').first.inner_text() == ''
            phone.locator('.bonus-row').first.locator('[data-action="bonusReveal"]').click()
            board_wait('FM.rows[0][0].shown && FM.rows[0][0].ptsShown')
            expect(board.locator('#fmcol0 .fmrow .p').first).to_have_text('45')
            phone.locator('.bonus-row').first.locator('[data-action="bonusHide"]').click()
            board_wait('!FM.rows[0][0].shown')
            board.wait_for_timeout(1000)
            assert not board.evaluate('FM.rows[0][0].ptsShown')
            phone.locator('.bonus-row').first.locator('[data-action="bonusReveal"]').click()
            board_wait('FM.rows[0][0].ptsShown')
            phone.locator('#text1_0').fill('Black')
            phone.locator('#pts1_0').fill('33')
            phone.wait_for_timeout(900)
            board_wait("FM.rows[1][0].text === 'Black' && FM.rows[1][0].pts === 33")
            assert not board.evaluate('FM.rows[1][0].shown')
            assert post('bonus-second-answer', 'bonusSet', {'p':0,'i':1,'text':'Pumpkin','pts':50}).ok
            assert post('bonus-third-answer', 'bonusSet', {'p':0,'i':2,'text':'Who','pts':22}).ok
            board_wait("FM.rows[0][1].text === 'Pumpkin' && FM.rows[0][2].text === 'Who'")
            phone.get_by_role('button', name='Reveal all player 1', exact=True).click()
            phone.get_by_role('button', name='Reveal all player 1', exact=True).click()
            board_wait('FM.rows[0][1].shown')
            assert not board.evaluate('FM.rows[0][2].shown')
            board_wait('FM.rows[0][2].ptsShown')
            phone.locator('#mask').click()
            board_wait('FM.mask')
            expect(board.locator('#fmcol0')).to_have_class('fmcol masked')
            phone.get_by_role('button', name='Start 25 sec', exact=True).click()
            board_wait('FM.timer !== null && FM.left <= 25')
            phone.get_by_role('button', name='Stop', exact=True).click()
            board_wait('FM.timer === null')
            phone.get_by_role('button', name='Reset timer to 20', exact=True).click()
            board_wait('FM.timer === null && FM.left === 20')
            phone.get_by_role('button', name='Start 25 sec', exact=True).click()
            board_wait('FM.timer !== null')
            phone.reload()
            expect(phone.locator('#text0_0')).to_have_value('Orange')
            board.reload()
            board.locator('#splash').click()
            board_wait("FM.rows[0][0].text === 'Orange' && FM.timer === null")
            assert board.evaluate('S.r') == 2
            expect(board.locator('#hostPanelBtn')).to_be_hidden()
            expect(phone.locator('#time')).to_contain_text('Paused')
            phone.evaluate('scrollTo(0,0)')
            shot(phone, 'phone-bonus.png')
            shot(board, 'board-bonus.png')
            assert phone.evaluate('document.documentElement.scrollWidth <= innerWidth')
            # Stop board heartbeats long enough to disable phone actions. Laptop stays private.
            board.route('**/phone/sync', lambda route: route.abort())
            expect(phone.locator('#connection')).to_contain_text('disconnected', timeout=10000)
            expect(phone.locator('#mask')).to_be_disabled()
            expect(board.locator('#hostPanelBtn')).to_be_hidden()
            board.unroute('**/phone/sync')
            expect(phone.locator('#connection')).to_contain_text('Connected', timeout=10000)
            # A missing phone heartbeat must not reveal private laptop controls, even after refresh.
            phone.route('**/phone/state', lambda route: route.abort())
            expect(board.locator('#phoneStatus')).to_contain_text('Phone disconnected', timeout=10000)
            expect(board.locator('#hostPanelBtn')).to_be_hidden()
            board.reload()
            board.locator('#splash').click()
            expect(board.locator('#hostPanelBtn')).to_be_hidden()
            phone.unroute('**/phone/state')
            expect(phone.locator('#connection')).to_contain_text('Connected', timeout=10000)
            # A second board lease freezes the old window and preserves the snapshot.
            newer = browser.new_context(viewport={'width':1440,'height':1000}).new_page()
            newer.goto(board_url)
            newer.locator('#splash').click()
            expect(board.locator('#phoneStatus')).to_contain_text('replaced')
            expect(phone.locator('#connection')).to_contain_text('Connected')
            newer.wait_for_function("FM.rows[0][0].text === 'Orange'")
            phone.once('dialog', lambda dialog: dialog.accept())
            phone.get_by_role('button', name='Clear bonus board', exact=True).click()
            newer.wait_for_function("FM.rows[0][0].text === '' && FM.left === 20")
            phone.once('dialog', lambda dialog: dialog.accept())
            phone.get_by_role('button', name='Disconnect phone', exact=True).click()
            expect(phone.locator('#connection')).to_contain_text('Phone disconnected')
            expect(newer.locator('#hostPanelBtn')).to_be_visible()
            new_info = json.load(urlopen(Request(origin + '/phone/info', headers={'Authorization': 'Bearer ' + nonce})))
            assert new_info['host_token'] != host_token
            browser.close()
    finally:
        for server in (companion, fixture):
            if server:
                server.shutdown()
                server.server_close()
    print('PASS: paired phone host browsers')

if __name__ == '__main__':
    main()
