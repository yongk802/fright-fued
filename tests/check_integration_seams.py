"""Focused browser regressions, run before and after adapting the supplied HTML."""
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread

from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[1]


def main():
    server = ThreadingHTTPServer(("127.0.0.1", 0), partial(SimpleHTTPRequestHandler, directory=str(ROOT)))
    Thread(target=server.serve_forever, daemon=True).start()
    errors = []
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1280, "height": 960})
            page.goto(f"http://127.0.0.1:{server.server_port}/")
            page.set_content('<iframe sandbox="allow-scripts allow-same-origin allow-popups allow-modals" allow="fullscreen" src="/index.html" width="1200" height="900"></iframe>')
            frame = page.frames[1]
            frame.locator("#startBtn").click()
            frame.locator("#navBonus").click()
            page.evaluate("""() => document.querySelector('iframe').contentWindow.postMessage({ff:'host',cmd:'start',s:99}, '*')""")
            page.wait_for_timeout(100)
            if frame.locator("#timer").inner_text() != "20":
                errors.append("Unrelated parent window can send host commands")
            frame.evaluate("""() => {
              window.webkitCalls = 0;
              Object.defineProperty(document.documentElement, 'requestFullscreen', {value: undefined, configurable:true});
              document.documentElement.webkitRequestFullscreen = () => {window.webkitCalls++};
            }""")
            frame.locator("#fsBtn").click()
            if frame.evaluate("window.webkitCalls") != 1:
                errors.append("Older Safari fullscreen API was not called")
            browser.close()
    finally:
        server.shutdown()
        server.server_close()
    for error in errors:
        print("FAIL:", error)
    assert not errors, errors
    print("PASS: popup sender validation and older Safari fullscreen")


if __name__ == "__main__":
    main()
