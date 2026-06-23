"""Browser verification for /chart?category=tx_fut_net.

Checks:
  - the requested category is selected
  - legend text is rendered
  - at least one uPlot canvas is present
  - the canvas contains non-blank pixels
  - no browser console errors were emitted
  - a screenshot is written for visual review
"""
from __future__ import annotations

from pathlib import Path
from playwright.sync_api import sync_playwright


ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "_analysis"
URL_DIRECT = "http://127.0.0.1:8000/chart?category=tx_fut_net"
URL_DEFAULT = "http://127.0.0.1:8000/chart"


def check_page(page, screenshot: Path) -> dict[str, object]:
    page.wait_for_selector("#chartArea canvas", timeout=15_000)
    selected = page.locator("#categorySelect").input_value()
    legend = page.locator("#legend").inner_text(timeout=5_000)
    canvas_count = page.locator("#chartArea canvas").count()
    pixel_stats = page.evaluate(
        """
        () => {
          const canvases = [...document.querySelectorAll('#chartArea canvas')];
          let colored = 0;
          let sampled = 0;
          for (const c of canvases) {
            const ctx = c.getContext('2d');
            const data = ctx.getImageData(0, 0, c.width, c.height).data;
            const step = 40;
            for (let y = 0; y < c.height; y += step) {
              for (let x = 0; x < c.width; x += step) {
                const i = (y * c.width + x) * 4;
                const r = data[i], g = data[i + 1], b = data[i + 2], a = data[i + 3];
                sampled++;
                if (a > 0 && (r < 245 || g < 245 || b < 245)) colored++;
              }
            }
          }
          return { colored, sampled, ratio: sampled ? colored / sampled : 0 };
        }
        """
    )
    page.screenshot(path=str(screenshot), full_page=True)
    return {
        "selected": selected,
        "legend": legend,
        "canvas_count": canvas_count,
        "pixel_stats": pixel_stats,
        "screenshot": str(screenshot),
    }


def assert_result(name: str, result: dict[str, object], errors: list[str]) -> None:
    failures = []
    if result["selected"] != "tx_fut_net":
        failures.append(f"categorySelect={result['selected']!r}")
    legend = str(result["legend"])
    if "台指期法人淨部位" not in legend or "台指期近月收盤" not in legend:
        failures.append(f"legend missing expected text: {legend!r}")
    if int(result["canvas_count"]) < 1:
        failures.append(f"canvas_count={result['canvas_count']}")
    pixel_stats = result["pixel_stats"]
    if pixel_stats["ratio"] < 0.01:
        failures.append(f"canvas appears blank: {pixel_stats}")
    if errors:
        failures.append("console errors: " + " | ".join(errors[:5]))
    print(f"[{name}] {result}")
    if failures:
        raise SystemExit(f"VERIFY FAILED ({name}): " + "; ".join(failures))


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    errors: list[str] = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)

        page = browser.new_page(viewport={"width": 1440, "height": 900})
        page.on("console", lambda msg: errors.append(msg.text) if msg.type == "error" else None)
        page.goto(URL_DIRECT, wait_until="networkidle", timeout=30_000)
        assert_result("desktop direct URL", check_page(page, OUT_DIR / "tx_fut_net_chart.png"), errors)

        errors.clear()
        page.goto(URL_DEFAULT, wait_until="networkidle", timeout=30_000)
        page.locator("#categorySelect").select_option("tx_fut_net")
        assert_result(
            "desktop manual select",
            check_page(page, OUT_DIR / "tx_fut_net_chart_manual_select.png"),
            errors,
        )

        errors.clear()
        mobile = browser.new_page(viewport={"width": 390, "height": 844}, is_mobile=True)
        mobile.on("console", lambda msg: errors.append(msg.text) if msg.type == "error" else None)
        mobile.goto(URL_DIRECT, wait_until="networkidle", timeout=30_000)
        assert_result("mobile direct URL", check_page(mobile, OUT_DIR / "tx_fut_net_chart_mobile.png"), errors)

        browser.close()
    print("VERIFY OK")


if __name__ == "__main__":
    main()
