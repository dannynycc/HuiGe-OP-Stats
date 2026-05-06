"""Capture screenshots of all 4 chart modes."""
import asyncio
from playwright.async_api import async_playwright

MODES = ["stacked", "original", "scatter", "heatmap"]

async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch()
        page = await b.new_page(viewport={"width": 1600, "height": 950})
        await page.goto("http://127.0.0.1:8765/chart", wait_until="networkidle")
        await page.wait_for_timeout(1500)
        for m in MODES:
            await page.click(f'.mode-btn[data-mode="{m}"]')
            await page.wait_for_timeout(800)
            path = rf"D:\ClaudeCode\法人OP日夜盤數據\chart_{m}.png"
            await page.screenshot(path=path, full_page=False)
            n_canvas = await page.evaluate(
                "document.querySelectorAll('#chartArea canvas').length"
            )
            n_grid = await page.evaluate(
                "document.querySelectorAll('#chartArea .panel').length"
            )
            print(f"mode={m}: canvases={n_canvas} panels={n_grid}")
        await b.close()

asyncio.run(main())
