"""Verify main view actually renders close_price for 電子期/金融期 across multiple historical dates.

Uses Playwright to render the page (so JS runs), checks actual DOM cells.
"""
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
from playwright.sync_api import sync_playwright

DATES = [
    "2020-03-26",
    "2021-08-16",
    "2024-06-11",
    "2025-04-15",
    "2025-08-18",
    "2026-04-15",
    "2026-05-06",
]

def main():
    failures = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(viewport={"width": 1400, "height": 900})
        page = ctx.new_page()
        for vd in DATES:
            page.goto(f"http://127.0.0.1:8765/?view_date={vd}", wait_until="networkidle", timeout=20000)
            # Pull the rendered table
            cells = page.evaluate("""() => {
                const rows = document.querySelectorAll('tbody tr');
                const out = [];
                for (const r of rows) {
                    const tds = r.querySelectorAll('td');
                    if (tds.length < 4) continue;
                    out.push({
                        product: tds[0].innerText.trim(),
                        close: tds[3].innerText.trim(),  // 4th col = close
                    });
                }
                return out;
            }""")
            te = next((c for c in cells if "電子" in c["product"]), None)
            tf = next((c for c in cells if "金融" in c["product"]), None)
            tx = next((c for c in cells if "台指" in c["product"]), None)
            te_close = te["close"] if te else "(no row)"
            tf_close = tf["close"] if tf else "(no row)"
            tx_close = tx["close"] if tx else "(no row)"
            ok = bool(te_close.strip()) and bool(tf_close.strip()) and bool(tx_close.strip())
            mark = "✓" if ok else "❌ EMPTY"
            print(f"{vd}: TX='{tx_close}'  TE='{te_close}'  TF='{tf_close}'  {mark}")
            if not ok:
                failures.append(vd)
        browser.close()
    print()
    if failures:
        print(f"FAILED dates: {failures}")
        sys.exit(1)
    print("ALL PASS")

if __name__ == "__main__":
    main()
