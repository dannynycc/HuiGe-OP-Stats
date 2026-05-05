"""FastAPI app — manual refresh + read endpoints."""
from __future__ import annotations
import logging
from pathlib import Path
from typing import Any
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from .db import connect, init_db
from .refresh import refresh
from .dashboard import build_dashboard

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(name)s | %(message)s")

ROOT = Path(__file__).resolve().parent
STATIC = ROOT / "static"

app = FastAPI(title="法人OP日夜盤數據", docs_url="/docs")
init_db()

app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC / "index.html")


@app.post("/api/refresh")
def api_refresh(date: str | None = None) -> dict[str, Any]:
    """Trigger a refresh. date='YYYY-MM-DD' optional, defaults to latest weekday."""
    return refresh(date)


@app.get("/api/today")
def api_today(date: str | None = Query(default=None)) -> dict[str, Any]:
    """All today's tables for a given date (defaults to most recent date in DB)."""
    with connect() as con:
        if not date:
            row = con.execute("SELECT MAX(date) FROM op_legal").fetchone()
            date = row[0] if row else None
        if not date:
            raise HTTPException(404, "No data in DB. Run /api/refresh first.")

        op_day = [dict(r) for r in con.execute(
            "SELECT * FROM op_legal WHERE date=? AND daynight='day' ORDER BY product, callput, role",
            (date,)
        )]
        op_night = [dict(r) for r in con.execute(
            "SELECT * FROM op_legal WHERE date=? AND daynight='night' ORDER BY product, callput, role",
            (date,)
        )]
        fut_day = [dict(r) for r in con.execute(
            "SELECT * FROM fut_legal WHERE date=? AND daynight='day' ORDER BY product, role",
            (date,)
        )]
        fut_night = [dict(r) for r in con.execute(
            "SELECT * FROM fut_legal WHERE date=? AND daynight='night' ORDER BY product, role",
            (date,)
        )]
        fut_price = [dict(r) for r in con.execute(
            "SELECT * FROM fut_price WHERE date=? ORDER BY expiry",
            (date,)
        )]
        credit_twse = [dict(r) for r in con.execute(
            "SELECT * FROM credit_twse WHERE date=? ORDER BY rowid",
            (date,)
        )]
        credit_summary_row = con.execute(
            "SELECT * FROM credit_summary WHERE date=?", (date,)
        ).fetchone()
        daily_row = con.execute(
            "SELECT * FROM daily_summary WHERE date=?", (date,)
        ).fetchone()
        last_refresh = con.execute(
            "SELECT * FROM refresh_log ORDER BY id DESC LIMIT 1"
        ).fetchone()

        return {
            "date": date,
            "op_day": op_day,
            "op_night": op_night,
            "fut_day": fut_day,
            "fut_night": fut_night,
            "fut_price": fut_price,
            "credit_twse": credit_twse,
            "credit_summary": dict(credit_summary_row) if credit_summary_row else None,
            "daily_summary": dict(daily_row) if daily_row else None,
            "last_refresh": dict(last_refresh) if last_refresh else None,
        }


@app.get("/api/timeseries")
def api_timeseries() -> dict[str, Any]:
    """Full daily_summary history for charts."""
    with connect() as con:
        rows = [dict(r) for r in con.execute(
            "SELECT * FROM daily_summary ORDER BY date"
        )]
    return {"rows": rows}


@app.get("/api/dashboard")
def api_dashboard(date: str | None = Query(default=None)) -> dict[str, Any]:
    """The 6-row 柴柴 法人部位彙整 view for a given data date."""
    with connect() as con:
        if not date:
            row = con.execute("SELECT MAX(date) FROM fut_legal").fetchone()
            date = row[0] if row else None
        if not date:
            raise HTTPException(404, "No data in DB. Run /api/refresh first.")
    payload = build_dashboard(date)
    # also include last_refresh for display
    with connect() as con:
        last = con.execute(
            "SELECT * FROM refresh_log ORDER BY id DESC LIMIT 1"
        ).fetchone()
        payload["last_refresh"] = dict(last) if last else None
    return payload


@app.get("/api/dates")
def api_dates() -> dict[str, Any]:
    """List available dates (from op_legal) so UI can populate a date picker."""
    with connect() as con:
        rows = [r[0] for r in con.execute(
            "SELECT DISTINCT date FROM op_legal ORDER BY date DESC"
        )]
    return {"dates": rows}
