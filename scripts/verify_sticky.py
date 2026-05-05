"""Verify comprehensive.html sticky thead works correctly using Playwright.
Renders page, waits for fetch, takes 3 screenshots: top, scrolled-300, scrolled-800.
"""
import sys, pathlib
from playwright.sync_api import sync_playwright

OUT = pathlib.Path(r"C:\Users\Home\AppData\Local\Temp")

def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(viewport={"width": 1900, "height": 800})
        page = ctx.new_page()
        page.goto("http://127.0.0.1:8765/static/comprehensive.html",
                  wait_until="networkidle", timeout=30000)
        # ensure body rendered (rows present)
        page.wait_for_selector("table.zonghe tbody tr td:not([colspan])", timeout=10000)

        page.screenshot(path=str(OUT / "sticky_top.png"), full_page=False)
        # scroll the .table-wrap not the window
        page.evaluate("document.querySelector('.table-wrap').scrollTop = 300")
        page.wait_for_timeout(200)
        page.screenshot(path=str(OUT / "sticky_300.png"), full_page=False)

        page.evaluate("document.querySelector('.table-wrap').scrollTop = 800")
        page.wait_for_timeout(200)
        page.screenshot(path=str(OUT / "sticky_800.png"), full_page=False)

        # also probe: did thead actually stick? (its bounding rect top should be ~ wrap top)
        info = page.evaluate("""() => {
            const wrap = document.querySelector('.table-wrap');
            const r1 = document.querySelectorAll('table.zonghe thead tr')[0].querySelector('th');
            const r2 = document.querySelectorAll('table.zonghe thead tr')[1].querySelector('th');
            const wRect = wrap.getBoundingClientRect();
            const r1Rect = r1.getBoundingClientRect();
            const r2Rect = r2.getBoundingClientRect();
            return {
                wrapTop: wRect.top, wrapHeight: wRect.height,
                r1Top: r1Rect.top, r1Height: r1Rect.height,
                r2Top: r2Rect.top, r2Height: r2Rect.height,
                scrollTop: wrap.scrollTop,
            };
        }""")
        print("scrolled-800 layout:", info)
        gap = info["r2Top"] - (info["r1Top"] + info["r1Height"])
        print(f"gap r1->r2: {gap:.2f}px (should be 0)")
        print(f"r1 stuck to wrap top: {abs(info['r1Top'] - info['wrapTop']) < 1}")
        browser.close()

if __name__ == "__main__":
    main()
