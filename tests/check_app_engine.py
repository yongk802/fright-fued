"""Exercise a disposable real App Engine serving the packaged Fright Feud app.

Start an isolated engine with this app as its only catalog entry, then run:
python3 tests/check_app_engine.py --url http://127.0.0.1:19937
Requires Playwright/Chromium only in the development environment.
"""
import argparse
import json
from pathlib import Path
import re
from urllib.parse import urlparse

from playwright.sync_api import expect, sync_playwright


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:19937")
    parser.add_argument("--screenshots", type=Path, default=Path("test-results"))
    args = parser.parse_args()
    args.screenshots.mkdir(parents=True, exist_ok=True)
    errors, external = [], []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1440, "height": 1100}, reduced_motion="reduce")

        def route(request_route):
            hostname = urlparse(request_route.request.url).hostname or ""
            if hostname in {"localhost", "127.0.0.1"} or hostname.endswith(".localhost"):
                request_route.continue_()
            else:
                external.append(request_route.request.url)
                request_route.abort()

        context.route("**/*", route)
        context.on("page", lambda page: page.on("pageerror", lambda error: errors.append(str(error))))
        page = context.new_page()
        page.goto(args.url)
        page.wait_for_load_state("networkidle")
        page.locator('button[data-app-id="fright-feud"]').click()
        game = page.frame_locator('iframe[title="Fright Feud"]')
        expect(game.locator("#startBtn")).to_be_visible()
        page.wait_for_load_state("networkidle")
        page.screenshot(path=str(args.screenshots / "setup.png"), full_page=True)
        game.locator("#t1").fill("The Witches")
        game.locator("#t2").fill("The Werewolves")
        game.locator("#startBtn").click()
        game.locator("#soundBtn").click()
        game.locator('.tile[aria-label="Answer 1"]').click()
        expect(game.locator("#potVal")).to_have_text("28")
        game.locator("#board").press("1")
        expect(game.locator("#potVal")).to_have_text("28")
        game.locator("#board").press("q")
        expect(game.locator("#team0")).to_have_class(re.compile("active"))
        game.locator("#board").press("p")
        expect(game.locator("#team0")).to_have_class(re.compile("active"))
        game.locator("#board").press("b")
        game.locator("#board").press("p")
        game.locator("#board").press("x")
        expect(game.locator("#team1 .xslot.hit")).to_have_count(1)
        game.locator("#team1 .xslot.hit").click()
        expect(game.locator("#team1 .xslot.hit")).to_have_count(0)
        game.locator("#award0").click()
        expect(game.locator("#team0 .tscore")).to_have_text("28")
        game.locator("#award0").click()
        expect(game.locator("#team0 .tscore")).to_have_text("28")
        game.locator("#nextBtn").click()
        expect(game.locator("#rndLbl")).to_have_text("Round 2 of 8")
        expect(game.locator("#potVal")).to_have_text("0")
        game.locator("#board").press("1")
        expect(game.locator("#potVal")).to_have_text("32")
        expect(game.locator("#xover")).to_be_hidden()
        expect(game.locator("#qText")).to_have_text("Name something you'd find in a haunted house")
        page.screenshot(path=str(args.screenshots / "main-game.png"), full_page=True)
        for _ in range(5):
            game.locator("#nextBtn").click()
        expect(game.locator("#rndLbl")).to_have_text("Round 7 of 8")
        game.locator("#board").press("1")
        expect(game.locator("#potVal")).to_have_text("68")
        game.locator("#award1").click()
        expect(game.locator("#team1 .tscore")).to_have_text("68")
        page.once("dialog", lambda dialog: dialog.accept("123"))
        game.locator('[data-adjust="0"]').click()
        expect(game.locator("#team0 .tscore")).to_have_text("123")
        game.locator("#fsBtn").click()
        frame = next(frame for frame in page.frames if frame.name == "" and "/apps/fright-feud/" in frame.url)
        page.wait_for_function("document.fullscreenElement !== null")
        game.locator("#fsBtn").click()
        page.wait_for_function("document.fullscreenElement === null")
        with context.expect_page() as key_info:
            game.locator("#keyBtn").click()
        key = key_info.value
        expect(key.get_by_role("heading", name="Fright Feud answer key")).to_be_visible()
        expect(key.locator("section")).to_have_count(13)
        key.close()
        game.locator("#navBonus").click()
        with context.expect_page() as host_info:
            game.locator("#hostPanelBtn").click()
        host = host_info.value
        expect(host.locator("#conn.ok")).to_have_text("Connected to the game")
        host.locator("#c0_0 .chips button").first.click()
        expect(game.locator("#fmcol0 .fmrow .a").first).to_have_text("")
        expect(game.locator("#fmTotal")).to_have_text("0")
        host.locator("#c0_0 .acts .go").click()
        expect(game.locator("#fmcol0 .fmrow .a").first).to_have_text("Orange")
        expect(game.locator("#fmTotal")).to_have_text("45")
        host.locator("#s25").click()
        expect(game.locator("#fmcol0")).to_have_class(re.compile("masked"))
        expect(game.locator("#timer")).to_have_text("25")
        host.locator("#stp").click()
        host.locator("#msk").click()
        expect(game.locator("#fmcol0")).not_to_have_class(re.compile("masked"))
        page.screenshot(path=str(args.screenshots / "bonus-game.png"), full_page=True)
        host.screenshot(path=str(args.screenshots / "host-controls.png"), full_page=True)
        host.close()
        with context.expect_page() as reopen_info:
            game.locator("#hostPanelBtn").click()
        reopened = reopen_info.value
        expect(reopened.locator("#conn.ok")).to_have_text("Connected to the game")
        expect(reopened.locator("#c0_0 input.t")).to_have_value("Orange")
        reopened.close()
        page.once("dialog", lambda dialog: dialog.accept())
        game.locator("#fmReset").click()
        expect(game.locator("#fmTotal")).to_have_text("0")
        expect(game.locator("#timer")).to_have_text("20")
        game.locator("#navGame").click()
        page.set_viewport_size({"width": 390, "height": 844})
        page.wait_for_function("document.querySelector('#sidebar').getBoundingClientRect().right <= 0")
        page.screenshot(path=str(args.screenshots / "narrow-game.png"), full_page=True)
        assert frame.evaluate("document.documentElement.scrollWidth <= window.innerWidth"), "Game overflows narrow screen"
        assert frame.evaluate("document.fonts.check('16px Creepster') && document.fonts.check('16px Oswald')"), "Local fonts unavailable"
        assert not errors, errors
        assert not external, external
        print(json.dumps({"result": "PASS", "page_errors": errors, "external_requests": external, "screenshots": str(args.screenshots.resolve())}, indent=2))
        context.close()
        browser.close()


if __name__ == "__main__":
    main()
