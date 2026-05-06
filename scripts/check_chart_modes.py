"""Capture screenshots covering both categories + all margin modes."""
import asyncio
from playwright.async_api import async_playwright

MODES = ["stacked", "original", "scatter"]

async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch()
        page = await b.new_page(viewport={"width": 1600, "height": 950})
        await page.goto("http://127.0.0.1:8765/chart", wait_until="networkidle")
        await page.wait_for_timeout(1500)

        # margin category, all 3 modes
        for m in MODES:
            await page.click(f'.mode-btn[data-mode="{m}"]')
            await page.wait_for_timeout(700)
            path = rf"D:\ClaudeCode\法人OP日夜盤數據\chart_margin_{m}.png"
            await page.screenshot(path=path, full_page=False)
            n_canvas = await page.evaluate(
                "document.querySelectorAll('#chartArea canvas').length"
            )
            print(f"category=margin mode={m}: canvases={n_canvas}")

        # switch to stock_fut
        await page.select_option("#categorySelect", "stock_fut")
        await page.wait_for_timeout(800)
        n_canvas = await page.evaluate(
            "document.querySelectorAll('#chartArea canvas').length"
        )
        bar_visible = await page.evaluate(
            "getComputedStyle(document.getElementById('modeBar')).display"
        )
        print(f"category=stock_fut: canvases={n_canvas}  modeBar display={bar_visible}")
        await page.screenshot(
            path=r"D:\ClaudeCode\法人OP日夜盤數據\chart_stockfut.png",
            full_page=False,
        )

        # switch back to margin and verify mode bar comes back
        await page.select_option("#categorySelect", "margin")
        await page.wait_for_timeout(800)
        bar_visible2 = await page.evaluate(
            "getComputedStyle(document.getElementById('modeBar')).display"
        )
        print(f"back to margin: modeBar display={bar_visible2}")

        await b.close()

asyncio.run(main())
