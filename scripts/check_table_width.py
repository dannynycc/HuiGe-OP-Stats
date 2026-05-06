"""Verify comprehensive table width fits viewport across multiple sizes."""
import asyncio
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch()
        for vw in (1280, 1366, 1600, 1920):
            page = await b.new_page(viewport={"width": vw, "height": 900})
            await page.goto("http://127.0.0.1:8765/comprehensive", wait_until="networkidle")
            await page.wait_for_timeout(700)
            info = await page.evaluate("""({
                viewport: window.innerWidth,
                table: document.querySelector('table.zonghe').scrollWidth,
                bodyScroll: document.body.scrollWidth,
                hScroll: document.documentElement.scrollWidth > document.documentElement.clientWidth
            })""")
            t = info["table"]; bs = info["bodyScroll"]; hs = info["hScroll"]
            print(f"vw={vw}: table_scrollW={t} body_scrollW={bs} h_overflow={hs}")
            await page.close()
        await b.close()

asyncio.run(main())
