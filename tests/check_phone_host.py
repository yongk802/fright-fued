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
            errors, external = [], []
            def monitor(context):
                context.on('page', lambda page: page.on('pageerror', lambda error: errors.append(str(error))))
                def local_only(route):
                    hostname = urlsplit(route.request.url).hostname or ''
                    if hostname in ('127.0.0.1', 'localhost') or hostname.endswith('.localhost'):
                        route.continue_()
                    else:
                        external.append(route.request.url)
                        route.abort()
                context.route('**/*', local_only)
                return context
            board = monitor(browser.new_context(viewport={'width': 1440, 'height': 1000})).new_page()
            board.goto(board_url)
            board.locator('#splash').click()
            expect(board.get_by_role('button', name='Connect phone', exact=True)).to_be_visible(timeout=4000)
            def board_wait(expression):
                board.wait_for_function(expression)
            def post(identifier, action, payload, generation=None):
                envelope = {'id':identifier, 'action':action, 'args':payload, 'game':board.evaluate('S.g')}
                if action == 'bonusSet':
                    if generation is None:
                        generation = phone.request.get(origin + '/phone/state', headers={'Authorization': 'Bearer ' + host_token}).json()['generation']
                    envelope['generation'] = generation
                return phone.request.post(origin + '/phone/command', headers={'Authorization': 'Bearer ' + host_token}, data=envelope)
            def shot(page, name):
                if args.screenshots:
                    args.screenshots.mkdir(parents=True, exist_ok=True)
                    if page.locator('#splash').count():
                        page.wait_for_function("getComputedStyle(document.getElementById('splash')).opacity === '0'")
                        expect(page.locator('#xover')).to_be_hidden()
                    page.screenshot(path=str(args.screenshots / name), full_page=not name.startswith('phone-'))
            with board.context.expect_page(timeout=3000) as pairing_info:
                board.get_by_role('button', name='Connect phone', exact=True).click()
            pairing = pairing_info.value
            expect(pairing.get_by_role('heading', name='Host from your phone')).to_be_visible()
            expect(pairing.locator('#phoneQR svg')).to_be_visible()
            pairing.wait_for_function("getComputedStyle(document.body).fontFamily.includes('Oswald')")
            pairing.evaluate('document.fonts.ready')
            shot(pairing, 'pairing-window.png')
            assert board.locator('#phonePair').count() == 0, 'Pairing must not cover the board'
            pages_before = len(board.context.pages)
            board.get_by_role('button', name='Connect phone', exact=True).click()
            board.wait_for_timeout(600)
            assert len(board.context.pages) == pages_before, 'Repeated clicks should reuse the pairing window'
            with pairing.expect_event('close'):
                pairing.get_by_role('button', name='Close', exact=True).click()
            assert pairing.is_closed()
            # A blocked popup needs a persistent hint, without restoring an overlay.
            board.evaluate('window.savedOpen = window.open; window.open = () => null')
            board.get_by_role('button', name='Connect phone', exact=True).click()
            expect(board.locator('#phoneStatus')).to_contain_text('Allow pop-ups')
            board.wait_for_timeout(700)
            expect(board.locator('#phoneStatus')).to_contain_text('Allow pop-ups')
            assert board.locator('#phonePair').count() == 0
            board.evaluate('window.open = window.savedOpen; delete window.savedOpen')
            with board.context.expect_page(timeout=3000) as reopened_info:
                board.get_by_role('button', name='Connect phone', exact=True).click()
            pairing = reopened_info.value
            expect(pairing.locator('#phoneQR svg')).to_be_visible()
            assert pairing.locator('#phoneURL').get_attribute('target') == '_blank'
            assert 'noopener' in pairing.locator('#phoneURL').get_attribute('rel')
            board.wait_for_function("AC && AC.state === 'running'")
            info = json.load(urlopen(Request(origin + '/phone/info', headers={'Authorization': 'Bearer ' + nonce})))
            host_token = info['host_token']
            phone_context = monitor(browser.new_context(viewport={'width':390, 'height':844}, is_mobile=True, has_touch=True))
            phone = phone_context.new_page()
            with pairing.expect_event('close', timeout=5000):
                phone.goto(origin + '/phone/#' + host_token)
                expect(phone.locator('#connection')).to_contain_text('Connected')
            assert pairing.is_closed(), 'Close the private pairing link after the phone connects'
            expect(board.locator('#startBtn')).to_be_hidden()
            board.evaluate('window.savedOpen = window.open; window.open = () => null')
            board.get_by_role('button', name='Connect phone', exact=True).click()
            board.wait_for_timeout(800)
            expect(board.locator('#phoneStatus')).to_contain_text('Allow pop-ups')
            board.evaluate('window.open = window.savedOpen; delete window.savedOpen')
            with board.context.expect_page(timeout=3000) as connected_pairing:
                board.get_by_role('button', name='Connect phone', exact=True).click()
            pairing = connected_pairing.value
            expect(pairing.locator('#phoneQR svg')).to_be_visible()
            board.wait_for_timeout(700)
            assert not pairing.is_closed(), 'The button should also work when a phone is already connected'
            with pairing.expect_event('close'):
                pairing.get_by_role('button', name='Close', exact=True).click()
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
            phone.evaluate('scrollTo(0,0)')
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
            # A debounced save held in transport must settle before a confirmed clear.
            held_saves, sent_actions = [], []
            def hold_first_save(route):
                command = route.request.post_data_json
                sent_actions.append(command['action'])
                if command['action'] == 'bonusSet' and command['args'].get('text') == 'Stale answer' and not held_saves:
                    held_saves.append(route)
                else:
                    route.continue_()
            phone.route('**/phone/command', hold_first_save)
            phone.locator('#text0_0').fill('Stale answer')
            phone.wait_for_timeout(450)
            assert len(held_saves) == 1
            phone.locator('#text0_0').fill('Obsolete queued answer')
            phone.wait_for_timeout(400)
            phone.once('dialog', lambda dialog: dialog.accept())
            phone.get_by_role('button', name='Clear bonus board', exact=True).click()
            phone.wait_for_timeout(400)
            assert 'bonusReset' not in sent_actions, 'Clear overtook an in-flight save'
            held_saves[0].continue_()
            phone.wait_for_timeout(1000)
            board_wait("FM.rows[0][0].text === ''")
            assert sent_actions == ['bonusSet', 'bonusReset']
            previous_generation = held_saves[0].request.post_data_json['generation']
            assert post('late-save-after-reset', 'bonusSet', {'p':0,'i':0,'text':'Late stale answer','pts':99}, generation=previous_generation).status in (400,409)
            phone.wait_for_timeout(500)
            assert board.evaluate('FM.rows[0][0].text') == ''
            phone.unroute('**/phone/command')
            phone.locator('#text0_0').fill('Orange')
            phone.wait_for_timeout(1200)
            expect(phone.locator('#text0_0')).to_be_focused()
            expect(phone.locator('#text0_0')).to_have_value('Orange')
            board_wait("FM.rows[0][0].text === 'Orange' && FM.rows[0][0].pts === 45")
            # A rejected save restores the board value even while its input retains focus.
            def reject_save(route):
                if route.request.post_data_json['action'] == 'bonusSet':
                    route.fulfill(status=400, content_type='application/json', body='{"error":"stale generation"}')
                else:
                    route.continue_()
            phone.route('**/phone/command', reject_save)
            phone.locator('#text0_0').fill('Rejected draft')
            expect(phone.locator('#text0_0')).to_have_value('Orange')
            expect(phone.locator('#text0_0')).to_be_focused()
            expect(phone.locator('#notice')).to_contain_text('Unsent edits were discarded')
            assert board.evaluate('FM.rows[0][0].text') == 'Orange'
            phone.unroute('**/phone/command')
            # Lost drafts must not survive reconnection and blank freshly rebuilt fields.
            phone.route('**/phone/command', lambda route: route.abort())
            phone.locator('#text0_0').fill('Lost edit')
            phone.route('**/phone/state', lambda route: route.abort())
            expect(phone.locator('#connection')).to_contain_text('Connection lost', timeout=5000)
            phone.wait_for_timeout(700)
            phone.unroute('**/phone/command')
            phone.unroute('**/phone/state')
            expect(phone.locator('#connection')).to_contain_text('Connected', timeout=5000)
            phone.get_by_role('button', name='Main game', exact=True).click()
            expect(phone.locator('#pot')).to_be_visible()
            phone.get_by_role('button', name='Bonus round', exact=True).click()
            expect(phone.locator('#text0_0')).to_have_value('Orange')
            expect(phone.locator('#pts0_0')).to_have_value('45')
            phone.locator('.bonus-row').first.locator('[data-action="bonusReveal"]').click()
            board_wait("FM.rows[0][0].text === 'Orange' && FM.rows[0][0].shown")
            phone.locator('.bonus-row').first.locator('[data-action="bonusHide"]').click()
            board_wait('!FM.rows[0][0].shown')
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
            phone.locator('.bonus-row').first.scroll_into_view_if_needed()
            shot(phone, 'phone-bonus-entry.png')
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
            newer = monitor(browser.new_context(viewport={'width':1440,'height':1000})).new_page()
            newer.goto(board_url)
            newer.locator('#splash').click()
            expect(board.locator('#phoneStatus')).to_contain_text('replaced')
            expect(phone.locator('#connection')).to_contain_text('Connected')
            newer.wait_for_function("FM.rows[0][0].text === 'Orange'")
            phone.once('dialog', lambda dialog: dialog.accept())
            phone.get_by_role('button', name='Clear bonus board', exact=True).click()
            newer.wait_for_function("FM.rows[0][0].text === '' && FM.left === 20")
            # The entire four-game series can be hosted privately on the phone.
            phone.once('dialog', lambda dialog: dialog.accept())
            phone.get_by_role('button', name='New game', exact=True).click()
            expect(phone.locator('#gameSelect')).to_be_visible()
            phone.locator('#gameSelect').select_option('1')
            newer.wait_for_function('S.g === 1')
            phone.locator('#start').click()
            newer.wait_for_function('S.started && ROUNDS.length === 3')
            phone.get_by_role('button', name='Bonus round', exact=True).click()
            expect(phone.locator('body')).to_contain_text('Name a famous monster')
            phone.locator('#text0_0').fill('Frankenstein')
            newer.wait_for_function('FM.rows[0][0].pts === 35')
            phone.locator('.bonus-row').first.locator('[data-action="bonusReveal"]').click()
            newer.wait_for_function('FM.rows[0][0].ptsShown')
            phone.once('dialog', lambda dialog: dialog.accept())
            phone.get_by_role('button', name='Finish game and save result', exact=True).click()
            expect(phone.locator('.saved-results')).to_contain_text('Game 2')
            expect(phone.locator('.saved-results')).to_contain_text('Bonus: 35')
            newer.reload()
            newer.locator('#splash').click()
            newer.wait_for_function('RESULTS.length === 1 && RESULTS[0].game === 2')
            phone.reload()
            expect(phone.locator('.saved-results')).to_contain_text('Bonus: 35')
            phone.evaluate('scrollTo(0,0)')
            shot(phone, 'phone-series-results.png')
            assert phone.evaluate('document.documentElement.scrollWidth <= innerWidth')
            phone.once('dialog', lambda dialog: dialog.accept())
            phone.get_by_role('button', name='Clear saved results', exact=True).click()
            newer.wait_for_function('RESULTS.length === 0')
            expect(phone.locator('.saved-results')).to_have_count(0)
            with newer.context.expect_page(timeout=3000) as final_pairing:
                newer.get_by_role('button', name='Connect phone', exact=True).click()
            pairing = final_pairing.value
            expect(pairing.locator('#phoneQR svg')).to_be_visible()
            phone.once('dialog', lambda dialog: dialog.accept())
            with pairing.expect_event('close', timeout=5000):
                phone.get_by_role('button', name='Disconnect phone', exact=True).click()
            expect(phone.locator('#connection')).to_contain_text('Phone disconnected')
            expect(newer.locator('body')).not_to_have_class('phone-audience')
            expect(newer.locator('#startBtn')).to_be_visible()
            shot(newer, 'board-series-setup.png')
            newer.locator('#startBtn').click()
            newer.locator('#navBonus').click()
            expect(newer.locator('#hostPanelBtn')).to_be_visible()
            new_info = json.load(urlopen(Request(origin + '/phone/info', headers={'Authorization': 'Bearer ' + nonce})))
            assert new_info['host_token'] != host_token
            assert not errors, errors
            assert not external, external
            browser.close()
    finally:
        for server in (companion, fixture):
            if server:
                server.shutdown()
                server.server_close()
    print('PASS: paired phone host browsers')

if __name__ == '__main__':
    main()
