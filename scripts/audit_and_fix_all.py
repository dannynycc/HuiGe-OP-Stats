"""Comprehensive audit + auto-fix for daily_summary.

Run this after any backfill — it will:
  1. Audit NULL count by (year, column) — full table scan
  2. For each NULL, try every known fill strategy:
     - twse_margin_pct = margin_amt_oku / (mkt_cap_chao × 10000)
     - tpex_margin_pct = same logic for TPEX
     - op_cp_net = op_call_net - op_put_net
     - twse_mkt_cap_chao via weekly anchor × TWII ratio (interp)
     - 11 single-date NULL twse_margin_amt_oku via TWSE MI_MARGN historical
  3. Re-audit, list remaining NULL with root cause
  4. Sanity check: every column should be 0 NULL OR has documented limitation

Exits 0 if all clean, 1 if anything still NULL without documented reason.
"""
import sys
import io
import pathlib
import requests
import urllib3

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from app.db import connect

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

ALL_COLS = [
    "tx_close", "twii_close",
    "op_legal_net", "op_call_net", "op_put_net", "op_cp_net",
    "fut_pre_open_net", "stock_fut_legal_net",
    "twse_margin_amt_oku", "tpex_margin_amt_oku",
    "twse_mkt_cap_chao", "tpex_mkt_cap_chao",
    "twse_margin_pct", "tpex_margin_pct",
    "mkt_cap_source",
]


def audit_table(con, label: str) -> dict[str, int]:
    """Print + return NULL count per column."""
    total = con.execute("SELECT COUNT(*) FROM daily_summary").fetchone()[0]
    print(f"\n=== {label} (total {total} rows) ===")
    out: dict[str, int] = {}
    for c in ALL_COLS:
        n = con.execute(
            f"SELECT COUNT(*) FROM daily_summary WHERE {c} IS NULL"
        ).fetchone()[0]
        flag = "OK" if n == 0 else "XX"
        out[c] = n
        print(f"  [{flag}] {c:25s}: {n:4d} NULL ({n/total*100:5.1f}%)")
    return out


def fix_derived_pct(con) -> int:
    """twse_margin_pct + tpex_margin_pct from margin / mkt_cap."""
    n1 = con.execute("""
        UPDATE daily_summary
        SET twse_margin_pct = twse_margin_amt_oku / (twse_mkt_cap_chao * 10000.0)
        WHERE twse_margin_pct IS NULL
          AND twse_margin_amt_oku IS NOT NULL
          AND twse_mkt_cap_chao IS NOT NULL AND twse_mkt_cap_chao > 0
    """).rowcount
    n2 = con.execute("""
        UPDATE daily_summary
        SET tpex_margin_pct = tpex_margin_amt_oku / (tpex_mkt_cap_chao * 10000.0)
        WHERE tpex_margin_pct IS NULL
          AND tpex_margin_amt_oku IS NOT NULL
          AND tpex_mkt_cap_chao IS NOT NULL AND tpex_mkt_cap_chao > 0
    """).rowcount
    return n1 + n2


def fix_op_cp_net(con) -> int:
    return con.execute("""
        UPDATE daily_summary
        SET op_cp_net = op_call_net - op_put_net
        WHERE op_cp_net IS NULL
          AND op_call_net IS NOT NULL AND op_put_net IS NOT NULL
    """).rowcount


def fix_mkt_cap_interp(con) -> int:
    """For twse_mkt_cap_chao IS NULL, interpolate via weekly anchor + TWII."""
    nulls = list(con.execute("""
        SELECT date, twii_close FROM daily_summary
        WHERE twse_mkt_cap_chao IS NULL AND twii_close IS NOT NULL
    """))
    written = 0
    for d, twii_d in nulls:
        anchor = con.execute(
            """SELECT date, twse_mkt_cap_oku FROM mkt_cap_weekly
               WHERE date >= ? AND date < date(?, '+8 days')
               ORDER BY date LIMIT 1""", (d, d)
        ).fetchone() or con.execute(
            """SELECT date, twse_mkt_cap_oku FROM mkt_cap_weekly
               WHERE date < ? ORDER BY date DESC LIMIT 1""", (d,)
        ).fetchone()
        if not anchor:
            continue
        anchor_twii = con.execute(
            "SELECT twii_close FROM daily_summary WHERE date = ?", (anchor[0],)
        ).fetchone()
        if not anchor_twii or anchor_twii[0] is None:
            continue
        chao = anchor[1] * (twii_d / anchor_twii[0]) / 10000.0
        con.execute(
            """UPDATE daily_summary
               SET twse_mkt_cap_chao = ?, mkt_cap_source = 'interp'
               WHERE date = ?""", (chao, d)
        )
        written += 1
    return written


def fix_all_null_margin_via_twse(con) -> int:
    """For ALL NULL twse_margin_amt_oku (any era) fetch via TWSE MI_MARGN.

    WAF guards: sleep 1s between calls, give up & log if HTTP 307 (= banned)
    so we don't hammer for nothing.
    """
    import time as _time
    from app.scrapers import twse
    nulls = [r[0] for r in con.execute(
        "SELECT date FROM daily_summary WHERE twse_margin_amt_oku IS NULL ORDER BY date"
    )]
    if not nulls:
        return 0
    print(f"  fetching {len(nulls)} dates via TWSE MI_MARGN...")
    written = 0
    fail_streak = 0
    for i, d in enumerate(nulls, 1):
        # Up to 2 retries on transient None (TWSE sometimes returns empty on first try)
        thousand = None
        for retry in range(3):
            try:
                r = twse.fetch_credit(d)
                thousand = r.get("twse_margin_balance_thousand")
                if thousand is not None:
                    break
            except Exception:
                pass
            if retry < 2:
                _time.sleep(2)
        try:
            if thousand is None:
                fail_streak += 1
                if fail_streak >= 5:
                    print(f"  WAF blocked (5 consecutive fails @ {d}) — stopping early")
                    break
                continue
            fail_streak = 0
            oku = thousand / 100000
            con.execute(
                "UPDATE daily_summary SET twse_margin_amt_oku = ? WHERE date = ?",
                (oku, d),
            )
            # propagate to credit_summary
            existing = con.execute(
                "SELECT * FROM credit_summary WHERE date = ?", (d,)
            ).fetchone()
            con.execute(
                """INSERT OR REPLACE INTO credit_summary
                   (date, twse_margin_balance, twse_turnover, twse_mkt_cap,
                    tpex_margin_balance, tpex_turnover, tpex_mkt_cap)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (d, thousand,
                 existing["twse_turnover"] if existing else None,
                 existing["twse_mkt_cap"] if existing else None,
                 existing["tpex_margin_balance"] if existing else None,
                 existing["tpex_turnover"] if existing else None,
                 existing["tpex_mkt_cap"] if existing else None),
            )
            written += 1
            if i % 50 == 0:
                print(f"    [{i}/{len(nulls)}] {d}: {oku:.2f} 億 (cum {written})")
        except Exception as e:
            print(f"  {d} fetch err: {e!r}")
        _time.sleep(1.0)
    return written


def documented_irreparable(col: str, n: int) -> str | None:
    """Return reason if NULL is expected/documented, else None (= unexpected)."""
    return None  # We expect 0 NULL after all fixes. Anything left = real bug.


def main():
    print("STEP 1: BEFORE audit")
    with connect() as con:
        before = audit_table(con, "BEFORE fix")

    print("\nSTEP 2: Apply fix strategies")
    with connect() as con:
        # 1. Derived pct
        n_pct = fix_derived_pct(con)
        print(f"  derived pct (margin / mkt_cap): {n_pct} rows")

        # 2. op_cp_net
        n_cp = fix_op_cp_net(con)
        print(f"  op_cp_net = call - put: {n_cp} rows")

        # 3. mkt_cap interp
        n_mkt = fix_mkt_cap_interp(con)
        print(f"  mkt_cap interp (weekly × TWII): {n_mkt} rows")

        # 4. ALL NULL margin via TWSE MI_MARGN (any era)
        n_mgn = fix_all_null_margin_via_twse(con)
        print(f"  margin via TWSE MI_MARGN: {n_mgn} rows")

        # 5. Re-derive pct after margin filled
        n_pct2 = fix_derived_pct(con)
        print(f"  derived pct (round 2): {n_pct2} rows")

    print("\nSTEP 3: AFTER audit")
    with connect() as con:
        after = audit_table(con, "AFTER fix")

    # Diff
    print("\nSTEP 4: DELTA")
    for c in ALL_COLS:
        if before[c] != after[c]:
            print(f"  {c}: {before[c]} -> {after[c]} ({before[c] - after[c]} fixed)")

    # Final verdict
    print("\nSTEP 5: VERDICT")
    leftover = {c: n for c, n in after.items() if n > 0}
    if not leftover:
        print("  ALL CLEAN — 0 NULL across all columns ✓")
        return 0
    print(f"  {len(leftover)} columns still have NULL:")
    with connect() as con:
        for c, n in leftover.items():
            reason = documented_irreparable(c, n)
            if reason:
                print(f"    {c}: {n} NULL — {reason}")
            else:
                samples = [r[0] for r in con.execute(
                    f"SELECT date FROM daily_summary WHERE {c} IS NULL LIMIT 3"
                )]
                print(f"    {c}: {n} NULL — UNEXPECTED, sample dates: {samples}")
    return 1 if leftover else 0


if __name__ == "__main__":
    sys.exit(main())
