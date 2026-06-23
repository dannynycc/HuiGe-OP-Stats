"""產生 GitHub Pages 靜態網站到 docs/。

把 FastAPI /api 端點會回傳的 JSON 原樣倒成靜態檔，再把 app/static 的
HTML/JS 複製進 docs/，並針對「專案 Pages 子路徑」
(https://dannynycc.github.io/HuiGe-OP-Stats/) 改寫絕對路徑、注入 __STATIC__。

- 原始 app/static 完全不動 → 本機 FastAPI（含即時 refresh）照常可用。
- docs/ 是「產生物」，每次 CI / 本機跑此腳本都會重建；內容沒變的檔案
  git 不會產生 diff，所以只有真正更新的日期會被 commit。

用法：  python -m scripts.export_static    （從 repo 根目錄）
"""
from __future__ import annotations

import json
from pathlib import Path

from app.db import connect
from app.dashboard import build_dashboard
from app.main import api_comprehensive

ROOT = Path(__file__).resolve().parent.parent
STATIC_SRC = ROOT / "app" / "static"
DOCS = ROOT / "docs"
DATA = DOCS / "data"
DASH = DATA / "dashboard"

# 複製到 docs/ 的 HTML 需要的絕對路徑改寫（本機 FastAPI 靠路由，Pages 沒有）。
REWRITES = {
    'src="/static/app.js"': 'src="app.js"',
    'href="/comprehensive"': 'href="comprehensive.html"',
    'href="/chart"': 'href="chart.html"',
    'href="/"': 'href="index.html"',
}
MARKER = "<script>window.__STATIC__=true;</script>"


class _Resp:
    """api_comprehensive 只會往 response.headers 寫 cache 標頭，這裡給個空殼。"""

    def __init__(self) -> None:
        self.headers: dict[str, str] = {}


def _write_json(path: Path, obj: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(obj, ensure_ascii=False, default=str),
        encoding="utf-8",
    )


def _last_refresh(con) -> dict | None:
    row = con.execute(
        "SELECT * FROM refresh_log ORDER BY id DESC LIMIT 1"
    ).fetchone()
    return dict(row) if row else None


def export_data() -> int:
    """倒出所有 JSON。回傳產生的 dashboard 日期數。"""
    DASH.mkdir(parents=True, exist_ok=True)

    # 1) comprehensive.json — 直接呼叫真正的端點，保證 1:1 一致
    _write_json(DATA / "comprehensive.json", api_comprehensive(_Resp()))

    # 2) 日盤交易日清單（ascending）— 給前端把 view_date 換算成 data_date
    with connect() as con:
        day_dates = [
            r[0]
            for r in con.execute(
                "SELECT DISTINCT date FROM op_legal "
                "WHERE daynight='day' ORDER BY date"
            )
        ]
        last = _last_refresh(con)
    _write_json(DATA / "dates.json", {"dates": day_dates})

    # 3) 每個 data_date 一份 dashboard JSON + latest.json（預設視圖）
    for dd in day_dates:
        payload = build_dashboard(dd)
        payload["last_refresh"] = last
        _write_json(DASH / f"{dd}.json", payload)

    if day_dates:
        latest = build_dashboard(day_dates[-1])
        latest["last_refresh"] = last
        _write_json(DASH / "latest.json", latest)

    return len(day_dates)


def export_site() -> None:
    """複製 HTML/JS 到 docs/，改寫路徑並注入 __STATIC__。"""
    DOCS.mkdir(parents=True, exist_ok=True)

    # app.js 原樣複製（它在 runtime 自己看 window.__STATIC__）
    (DOCS / "app.js").write_text(
        (STATIC_SRC / "app.js").read_text(encoding="utf-8"),
        encoding="utf-8",
    )

    for name in ("index.html", "comprehensive.html", "chart.html"):
        html = (STATIC_SRC / name).read_text(encoding="utf-8")
        for a, b in REWRITES.items():
            html = html.replace(a, b)
        # marker 必須在任何讀 window.__STATIC__ 的 script 之前 → 放進 <head>
        html = html.replace("<head>", "<head>\n  " + MARKER, 1)
        (DOCS / name).write_text(html, encoding="utf-8")


def main() -> None:
    n = export_data()
    export_site()
    print(f"[export_static] docs/ 重建完成：{n} 個交易日 dashboard + comprehensive/dates")


if __name__ == "__main__":
    main()
