"""Backfill daily_summary.twii_close from TWSE MI_5MINS_HIST.

Endpoint: https://www.twse.com.tw/rwd/zh/TAIEX/MI_5MINS_HIST?date=YYYYMMDD&response=json
Returns ALL trading days in that month (one call per month).

Date string in response is ROC year format (e.g. '115/04/30' = 2026/04/30).
"""
import sys
import pathlib
import time
import argparse
import datetime as dt
import requests
import urllib3

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from app.db import connect

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

URL = "https://www.twse.com.tw/rwd/zh/TAIEX/MI_5MINS_HIST"
UA = "Mozilla/5.0"


def _to_float(s: str) -> float | None:
    if not s:
        return None
    try:
        return float(s.replace(",", ""))
    except (ValueError, AttributeError):
        return None


def _roc_to_iso(s: str) -> str | None:
    """'115/04/30' -> '2026-04-30'."""
    try:
        y, m, d = s.split("/")
        return f"{int(y) + 1911:04d}-{int(m):02d}-{int(d):02d}"
    except (ValueError, AttributeError):
        return None


def fetch_month(yyyymm: str) -> list[dict]:
    """yyyymm = '202604'. Returns list of {date, open, high, low, close}."""
    date_param = f"{yyyymm}01"
    r = requests.get(URL, params={"date": date_param, "response": "json"},
                     headers={"User-Agent": UA}, timeout=30, verify=False)
    r.raise_for_status()
    j = r.json()
    if j.get("stat") != "OK":
        return []
    out = []
    for row in j.get("data") or []:
        date = _roc_to_iso(row[0])
        if not date:
            continue
        out.append({
            "date": date,
            "twii_open": _to_float(row[1]),
            "twii_high": _to_float(row[2]),
            "twii_low":  _to_float(row[3]),
            "twii_close": _to_float(row[4]),
        })
    return out


def month_range(start: str, end: str):
    """yield 'YYYYMM' from start to end inclusive."""
    sy, sm = int(start[:4]), int(start[5:7])
    ey, em = int(end[:4]), int(end[5:7])
    y, m = sy, sm
    while (y, m) <= (ey, em):
        yield f"{y:04d}{m:02d}"
        m += 1
        if m > 12:
            m = 1
            y += 1


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--from", dest="start", default="2020-01")
    p.add_argument("--to", dest="end",
                   default=dt.date.today().strftime("%Y-%m"))
    p.add_argument("--sleep", type=float, default=0.5)
    args = p.parse_args()

    months = list(month_range(args.start, args.end))
    print(f"Fetching TWII for {len(months)} months ({args.start} ~ {args.end})")

    written = 0
    for i, ym in enumerate(months, 1):
        try:
            rows = fetch_month(ym)
        except Exception as e:
            print(f"  [{i:>3}/{len(months)}] {ym}: ERR {e!r}")
            continue
        if not rows:
            print(f"  [{i:>3}/{len(months)}] {ym}: 0 rows")
            time.sleep(args.sleep)
            continue
        with connect() as con:
            for row in rows:
                # only update twii_close (other twii_* not in schema yet)
                cur = con.execute(
                    "SELECT date FROM daily_summary WHERE date = ?", (row["date"],)
                ).fetchone()
                if cur:
                    con.execute(
                        "UPDATE daily_summary SET twii_close = ? WHERE date = ?",
                        (row["twii_close"], row["date"]),
                    )
                else:
                    con.execute(
                        "INSERT INTO daily_summary (date, twii_close) VALUES (?, ?)",
                        (row["date"], row["twii_close"]),
                    )
                written += 1
        print(f"  [{i:>3}/{len(months)}] {ym}: {len(rows)} days")
        time.sleep(args.sleep)

    print(f"\nDone. wrote/updated {written} daily rows.")


if __name__ == "__main__":
    main()
