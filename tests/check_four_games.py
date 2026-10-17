"""Behavioral regression for the four-game series and local host window."""
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from playwright.sync_api import sync_playwright, expect
ROOT = Path(__file__).resolve().parents[1]

def main():
    server = ThreadingHTTPServer(('127.0.0.1', 0), partial(SimpleHTTPRequestHandler, directory=str(ROOT)))
    Thread(target=server.serve_forever, daemon=True).start()
    errors = []
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page(viewport={'width':1280, 'height':900})
            page.on('pageerror', lambda e: errors.append(str(e)))
            page.goto(f'http://127.0.0.1:{server.server_port}/')
            page.locator('#splash').click()
            expect(page.locator('#gamePick button')).to_have_count(4)
            for game in range(4):
                page.locator('#gamePick button').nth(game).click()
                page.locator('#t1').fill('<Owls & Ghouls>')
                page.locator('#startBtn').click()
                expect(page.locator('#rndLbl')).to_have_text(f'Game {game+1} · Round 1 of 3')
                assert page.evaluate('S.teams[0].score === 0 && FM.left === 20 && FM.rows[0][0].text === ""')
                page.locator('#navBonus').click()
                if game == 0:
                    with page.expect_popup() as opened:
                        page.locator('#hostPanelBtn').click()
                    popup = opened.value
                    popup.on('pageerror', lambda e: errors.append(str(e)))
                expect(popup.locator('h1')).to_contain_text(f'Game {game+1}')
                expect(popup.locator('body')).to_contain_text(page.evaluate('BONUS[0].q'))
                page.evaluate('S.teams[0].score=123; FM.rows[0][0]={text:"Answer",pts:45,shown:true,ptsShown:true}; render(); fmRender()')
                page.once('dialog', lambda d: d.accept())
                page.locator('#finishBtn').click()
                expect(page.locator('#resultsBody tr')).to_have_count(game+1)
                expect(page.locator('#results')).to_contain_text('<Owls & Ghouls>')
            # Visiting setup and resuming must not strand delayed bonus reveals.
            page.locator('#startBtn').click()
            page.locator('#navBonus').click()
            page.evaluate('FM.rows[0][0]={text:"A",pts:5,shown:false,ptsShown:false}; FM.rows[0][1]={text:"B",pts:10,shown:false,ptsShown:false}; revealBonusPlayer(0)')
            page.once('dialog', lambda d: d.accept())
            page.locator('#navNew').click()
            page.locator('#navBonus').click()
            page.wait_for_function('FM.rows[0][0].ptsShown && FM.rows[0][1].ptsShown')
            page.reload()
            page.locator('#splash').click()
            expect(page.locator('#resultsBody tr')).to_have_count(4)
            expect(page.locator('#results')).to_contain_text('123')
            page.once('dialog', lambda d: d.accept())
            page.locator('#clearResults').click()
            page.reload()
            page.locator('#splash').click()
            expect(page.locator('#results')).to_be_hidden()
            assert not errors, errors
            browser.close()
    finally:
        server.shutdown(); server.server_close()
    print('PASS: four games, live host questions, saved results and clear')

if __name__ == '__main__': main()
