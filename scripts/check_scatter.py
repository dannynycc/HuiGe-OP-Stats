"""Re-shoot scatter mode."""
import asyncio
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch()
        page = await b.new_page(viewport={"width": 1600, "height": 950})
        await page.goto("http://127.0.0.1:8765/chart", wait_until="networkidle")
        await page.wait_for_timeout(1500)
        await page.click('.mode-btn[data-mode="scatter"]')
        await page.wait_for_timeout(800)
        await page.screenshot(
            path=r"D:\ClaudeCode\法人OP日夜盤數據\chart_scatter_plain.png",
            full_page=False,
        )
        await b.close()
asyncio.run(main())
