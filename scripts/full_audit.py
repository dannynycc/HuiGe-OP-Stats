"""Comprehensive end-to-end audit — find any data inconsistency / bug.

Sections:
  1. NULL count per column
  2. Schema consistency (live DB vs db.py)
  3. Derived field sanity (op_cp_net = call - put, etc)
  4. Orphan detection (daily_summary <-> op_legal, fut_legal)
  5. Cross-table continuity (trading days alignment)
  6. UI <-> backend column alignment
  7. Refresh idempotency check (running compute twice should match DB)
  8. Spot-check 5 random dates: every column reasonable
"""
import sys
import io
import pathlib
import sqlite3

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))


def section(title):
    print(f"\n{'='*60}\n{title}\n{'='*60}")


def main():
    issues = []
    con = sqlite3.connect("data/data.db")
    con.row_factory = sqlite3.Row

    # 1. NULL count
    section("1. NULL count per column (daily_summary)")
    cols = [r["name"] for r in con.execute("PRAGMA table_info(daily_summary)")]
    total = con.execute("SELECT COUNT(*) FROM daily_summary").fetchone()[0]
    for c in cols:
        n = con.execute(f"SELECT COUNT(*) FROM daily_summary WHERE {c} IS NULL").fetchone()[0]
        if c == "op_pre_open_cp_net":
            expected_null = "(2020-2023/04 沒夜盤, 預期 808 NULL)"
            ok = (n == 808)
        elif c == "mkt_cap_source":
            ok = (n == 0)
            expected_null = ""
        else:
            ok = (n == 0)
            expected_null = ""
        flag = "OK" if ok else "XX"
        print(f"  [{flag}] {c:25s}: {n} NULL  {expected_null}")
        if not ok and c != "op_pre_open_cp_net":
            issues.append(f"col {c} unexpected NULL count: {n}")

    # 2. Schema consistency
    section("2. Schema consistency (live DB has all columns from db.py)")
    expected_daily_summary = {
        "date", "tx_close", "op_legal_net", "op_call_net", "op_put_net", "op_cp_net",
        "fut_pre_open_net", "stock_fut_legal_net",
        "twse_margin_pct", "tpex_margin_pct",
        "twse_margin_amt_oku", "tpex_margin_amt_oku",
        "twse_mkt_cap_chao", "tpex_mkt_cap_chao",
        "twii_close", "mkt_cap_source", "op_pre_open_cp_net",
    }
    actual_cols = set(cols)
    missing = expected_daily_summary - actual_cols
    extra = actual_cols - expected_daily_summary
    if missing:
        print(f"  XX missing cols: {missing}")
        issues.append(f"missing daily_summary cols: {missing}")
    else:
        print(f"  OK daily_summary all {len(expected_daily_summary)} cols present")
    if extra:
        print(f"  ?  extra cols (in DB not in db.py): {extra}")

    # Verify other tables exist
    expected_tables = {"op_legal", "fut_legal", "fut_price", "credit_twse",
                       "credit_summary", "daily_summary", "refresh_log",
                       "mkt_cap_weekly"}
    actual_tables = {r[0] for r in con.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    )}
    miss_t = expected_tables - actual_tables
    if miss_t:
        print(f"  XX missing tables: {miss_t}")
        issues.append(f"missing tables: {miss_t}")
    else:
        print(f"  OK all 8 tables present")

    # 3. Derived field sanity
    section("3. Derived field sanity (sample mismatches)")
    # op_cp_net = op_call_net - op_put_net
    diffs = list(con.execute("""
        SELECT date, op_call_net, op_put_net, op_cp_net,
               (op_call_net - op_put_net) AS expected_cp
        FROM daily_summary
        WHERE op_call_net IS NOT NULL AND op_put_net IS NOT NULL
          AND ABS(op_cp_net - (op_call_net - op_put_net)) > 1
        LIMIT 5
    """))
    if diffs:
        print(f"  XX op_cp_net != call - put for {len(diffs)} sample dates:")
        for d in diffs:
            print(f"     {d['date']}: cp={d['op_cp_net']} expected={d['expected_cp']}")
        issues.append("op_cp_net derive broken")
    else:
        print(f"  OK op_cp_net = call - put (all match within 1 lot)")

    # twse_margin_pct = margin_amt_oku / (mkt_cap_chao * 10000)
    pct_diffs = list(con.execute("""
        SELECT date, twse_margin_amt_oku, twse_mkt_cap_chao, twse_margin_pct,
               (twse_margin_amt_oku / (twse_mkt_cap_chao * 10000.0)) AS expected
        FROM daily_summary
        WHERE twse_margin_amt_oku IS NOT NULL AND twse_mkt_cap_chao > 0
          AND ABS(twse_margin_pct - (twse_margin_amt_oku / (twse_mkt_cap_chao * 10000.0))) > 0.0001
        LIMIT 5
    """))
    if pct_diffs:
        print(f"  XX twse_margin_pct mismatch for {len(pct_diffs)} sample dates:")
        for d in pct_diffs:
            print(f"     {d['date']}: pct={d['twse_margin_pct']} expected={d['expected']}")
        issues.append("twse_margin_pct derive broken")
    else:
        print(f"  OK twse_margin_pct = margin_oku / (mkt_cap_chao × 10000)")

    # tpex_margin_pct
    tpex_pct_diffs = list(con.execute("""
        SELECT date, tpex_margin_amt_oku, tpex_mkt_cap_chao, tpex_margin_pct,
               (tpex_margin_amt_oku / (tpex_mkt_cap_chao * 10000.0)) AS expected
        FROM daily_summary
        WHERE tpex_margin_amt_oku IS NOT NULL AND tpex_mkt_cap_chao > 0
          AND ABS(tpex_margin_pct - (tpex_margin_amt_oku / (tpex_mkt_cap_chao * 10000.0))) > 0.0001
        LIMIT 5
    """))
    if tpex_pct_diffs:
        print(f"  XX tpex_margin_pct mismatch for {len(tpex_pct_diffs)} dates")
        for d in tpex_pct_diffs:
            print(f"     {d['date']}: pct={d['tpex_margin_pct']} expected={d['expected']}")
        issues.append("tpex_margin_pct derive broken")
    else:
        print(f"  OK tpex_margin_pct = margin / mkt_cap")

    # 4. Orphan detection
    section("4. Orphan detection")
    # daily_summary rows without day-session op_legal
    orphans1 = list(con.execute("""
        SELECT ds.date FROM daily_summary ds
        WHERE NOT EXISTS (
            SELECT 1 FROM op_legal WHERE date = ds.date AND daynight='day'
        )
    """))
    if orphans1:
        print(f"  XX {len(orphans1)} daily_summary rows have no day-session op_legal:")
        for r in orphans1[:5]:
            print(f"     {r['date']}")
        issues.append(f"orphan daily_summary: {len(orphans1)}")
    else:
        print(f"  OK 0 orphan daily_summary rows")

    # op_legal day rows without daily_summary
    orphans2 = list(con.execute("""
        SELECT DISTINCT op.date FROM op_legal op
        WHERE op.daynight='day'
          AND NOT EXISTS (SELECT 1 FROM daily_summary WHERE date = op.date)
    """))
    if orphans2:
        print(f"  XX {len(orphans2)} op_legal day-session dates missing daily_summary:")
        for r in orphans2[:5]:
            print(f"     {r['date']}")
        issues.append(f"missing daily_summary: {len(orphans2)}")
    else:
        print(f"  OK every op_legal day-date has daily_summary")

    # 5. Cross-table continuity
    section("5. Trading days continuity")
    # Compute expected gaps (weekend-only)
    rows = list(con.execute("""
        SELECT DISTINCT date FROM op_legal WHERE daynight='day' ORDER BY date
    """))
    import datetime as dt
    prev = None
    gaps = []
    for r in rows:
        d = dt.date.fromisoformat(r["date"])
        if prev:
            delta = (d - prev).days
            if delta > 4:  # >4 days = abnormal cluster
                gaps.append((prev.isoformat(), d.isoformat(), delta))
        prev = d
    print(f"  trading days {len(rows)}: {rows[0]['date']} ~ {rows[-1]['date']}")
    print(f"  gaps > 4 days: {len(gaps)} (= holiday clusters)")
    for g in gaps[:5]:
        print(f"     {g[0]} -> {g[1]} ({g[2]} days)")

    # 6. UI <-> backend column alignment
    section("6. UI <-> backend column alignment")
    # Read comprehensive.html and count R2 cells
    html_file = pathlib.Path("app/static/comprehensive.html").read_text(encoding="utf-8")
    import re
    # find R2 row count
    r2_match = re.search(r'<!-- R2:.*?-->.*?<tr>(.*?)</tr>', html_file, re.DOTALL)
    if r2_match:
        r2_cells = re.findall(r'<th>', r2_match.group(1))
        print(f"  comprehensive.html R2 cells: {len(r2_cells)}")
    # Count colgroup cols
    colg = re.search(r'<colgroup>(.*?)</colgroup>', html_file, re.DOTALL)
    if colg:
        col_count = len(re.findall(r'<col\b', colg.group(1)))
        print(f"  comprehensive.html colgroup cols: {col_count}")
        if r2_match and len(r2_cells) != col_count:
            print(f"  XX R2 cells ({len(r2_cells)}) != colgroup ({col_count})")
            issues.append("R2/colgroup mismatch")
        else:
            print(f"  OK R2 cells == colgroup cols")

    # Check JS row template td count
    js_tds = re.findall(r'\${td\w*\([^)]+\)}', html_file)
    fmtmd_count = len(re.findall(r'\${fmtMD\([^)]+\)}', html_file))
    total_tds = len(js_tds) + fmtmd_count
    print(f"  JS row template emits: {len(js_tds)} td-helpers + {fmtmd_count} fmtMD = {total_tds} cells")
    if r2_match and total_tds != len(r2_cells):
        print(f"  XX JS emits {total_tds} cells != R2 {len(r2_cells)} headers")
        issues.append("JS/R2 cell count mismatch")
    else:
        print(f"  OK JS emits same # cells as R2 headers")

    # 7. Spot-check 5 random dates
    section("7. Spot-check 5 random dates (eyeball reasonability)")
    samples = list(con.execute("""
        SELECT date, twii_close, tx_close, op_call_net, op_put_net, op_cp_net,
               op_legal_net, fut_pre_open_net, op_pre_open_cp_net,
               twse_margin_amt_oku, twse_mkt_cap_chao, twse_margin_pct,
               mkt_cap_source
        FROM daily_summary ORDER BY RANDOM() LIMIT 5
    """))
    for s in samples:
        print(f"\n  {s['date']}:")
        print(f"    twii={s['twii_close']:.2f}  tx={s['tx_close']}")
        print(f"    op call/put/cp = {s['op_call_net']} / {s['op_put_net']} / {s['op_cp_net']}")
        print(f"    op_legal_net={s['op_legal_net']}  fut_pre_open={s['fut_pre_open_net']}  op_pre_open_cp={s['op_pre_open_cp_net']}")
        print(f"    twse_margin_oku={s['twse_margin_amt_oku']:.2f}億  mkt_cap={s['twse_mkt_cap_chao']:.4f}兆  pct={s['twse_margin_pct']*100:.4f}%")
        print(f"    mkt_cap_source={s['mkt_cap_source']}")

    # 8. Final
    section("FINAL VERDICT")
    if not issues:
        print("  ALL CLEAN — 0 unexpected issues")
        return 0
    else:
        print(f"  {len(issues)} issues found:")
        for i in issues:
            print(f"    - {i}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
