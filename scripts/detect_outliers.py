"""Detect mkt_cap / margin outliers using multiple robust methods.

Methods:
1. **Weekly anchor cross-check**: For dates with mkt_cap_weekly entry, DB
   twse_mkt_cap_chao*10000 should EXACTLY match weekly oku. Any deviation
   > 0.5% = corrupt.

2. **TWII ratio constancy**: mkt_cap / TWII should be smooth. Compute
   rolling 21-day median ratio. Any single day's ratio off > 5% from rolling
   median = outlier.

3. **Day-over-day jump**: > 3% jump on adjacent trading days = suspicious
   (mkt_cap doesn't normally jump that much without TWII jumping similarly).

4. **Margin endpoint cross-check** (optional): Re-fetch TWSE MI_MARGN for
   every date and compare. Slow but ground truth.
"""
import sys
import io
import sqlite3

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")


def main():
    con = sqlite3.connect("data/data.db")
    con.row_factory = sqlite3.Row
    issues = []

    # 1. Weekly anchor cross-check
    print("=" * 60)
    print("1. Weekly anchor cross-check (mkt_cap_weekly vs daily_summary)")
    print("=" * 60)
    rows = list(con.execute("""
        SELECT w.date, w.twse_mkt_cap_oku AS weekly_oku,
               d.twse_mkt_cap_chao AS daily_chao,
               d.mkt_cap_source
        FROM mkt_cap_weekly w
        JOIN daily_summary d ON w.date = d.date
        WHERE d.twse_mkt_cap_chao IS NOT NULL
        ORDER BY w.date
    """))
    print(f"checked {len(rows)} weekly-anchor dates")
    mismatches = 0
    for r in rows:
        expected_chao = r["weekly_oku"] / 10000.0
        if abs(r["daily_chao"] - expected_chao) / expected_chao > 0.005:
            print(f"  XX {r['date']}: weekly={expected_chao:.4f}兆 daily={r['daily_chao']:.4f}兆 src={r['mkt_cap_source']}")
            mismatches += 1
            issues.append(("weekly_anchor", r["date"], expected_chao, r["daily_chao"]))
    print(f"mismatches: {mismatches}")

    # 2. TWII ratio constancy (rolling 21-day median, |z| > 3 = outlier)
    print()
    print("=" * 60)
    print("2. TWII × ratio cross-check (rolling 21-day median deviation)")
    print("=" * 60)
    rows = list(con.execute("""
        SELECT date, twse_mkt_cap_chao, twii_close
        FROM daily_summary
        WHERE twse_mkt_cap_chao IS NOT NULL AND twii_close IS NOT NULL
        ORDER BY date
    """))
    ratios = [r["twse_mkt_cap_chao"] / r["twii_close"] for r in rows]
    # Rolling 21-day median
    import statistics
    window = 21
    twii_outliers = 0
    for i in range(window, len(rows) - window):
        local = ratios[i - window:i + window + 1]
        med = statistics.median(local)
        # MAD = median absolute deviation
        mad = statistics.median([abs(x - med) for x in local])
        if mad == 0:
            continue
        # Robust z-score (modified z) = (x - med) / (1.4826 * mad)
        z = abs(ratios[i] - med) / (1.4826 * mad)
        if z > 5:  # 5-sigma outlier
            print(f"  XX {rows[i]['date']}: ratio={ratios[i]:.4f} (rolling med={med:.4f}, MAD-z={z:.1f})  mkt_cap={rows[i]['twse_mkt_cap_chao']:.4f} TWII={rows[i]['twii_close']:.2f}")
            twii_outliers += 1
            issues.append(("twii_ratio", rows[i]["date"], med * rows[i]["twii_close"], rows[i]["twse_mkt_cap_chao"]))
    print(f"outliers (5-sigma): {twii_outliers}")

    # 3. Day-over-day jump > 3%
    print()
    print("=" * 60)
    print("3. Day-over-day mkt_cap jump > 3% (TWII jump < 3%)")
    print("=" * 60)
    bigj = 0
    for i in range(1, len(rows)):
        prev_mc = rows[i - 1]["twse_mkt_cap_chao"]
        cur_mc = rows[i]["twse_mkt_cap_chao"]
        prev_tw = rows[i - 1]["twii_close"]
        cur_tw = rows[i]["twii_close"]
        mc_pct = (cur_mc - prev_mc) / prev_mc
        tw_pct = (cur_tw - prev_tw) / prev_tw
        # If mkt_cap jumps > 3% but TWII doesn't, suspicious
        if abs(mc_pct) > 0.03 and abs(mc_pct - tw_pct) > 0.03:
            print(f"  XX {rows[i]['date']}: mkt_cap {prev_mc:.2f}→{cur_mc:.2f} ({mc_pct*100:+.1f}%) but TWII {prev_tw:.0f}→{cur_tw:.0f} ({tw_pct*100:+.1f}%)")
            bigj += 1
            issues.append(("dod_jump", rows[i]["date"], None, cur_mc))
    print(f"jump anomalies: {bigj}")

    # 4. Margin vs mkt_cap ratio MAD-z (margin/mkt_cap should also be smooth)
    print()
    print("=" * 60)
    print("4. Margin/mkt_cap ratio MAD-z (rolling 21-day)")
    print("=" * 60)
    rows4 = list(con.execute("""
        SELECT date, twse_margin_amt_oku, twse_mkt_cap_chao
        FROM daily_summary
        WHERE twse_margin_amt_oku IS NOT NULL AND twse_mkt_cap_chao IS NOT NULL
        ORDER BY date
    """))
    margin_ratios = [r["twse_margin_amt_oku"] / (r["twse_mkt_cap_chao"] * 10000.0) for r in rows4]
    margin_outliers = 0
    for i in range(window, len(rows4) - window):
        local = margin_ratios[i - window:i + window + 1]
        med = statistics.median(local)
        mad = statistics.median([abs(x - med) for x in local])
        if mad == 0:
            continue
        z = abs(margin_ratios[i] - med) / (1.4826 * mad)
        if z > 5:
            d = rows4[i]["date"]
            print(f"  XX {d}: margin/mkt_cap={margin_ratios[i]*100:.4f}% (rolling med={med*100:.4f}% z={z:.1f})  margin={rows4[i]['twse_margin_amt_oku']:.2f}億  mkt_cap={rows4[i]['twse_mkt_cap_chao']:.4f}兆")
            margin_outliers += 1
            issues.append(("margin_ratio", d, med * rows4[i]["twse_mkt_cap_chao"] * 10000, rows4[i]["twse_margin_amt_oku"]))
    print(f"margin outliers: {margin_outliers}")

    # 5. Day-over-day margin jump > 5% AND TWII jump < 3% (= 不是市場大跌)
    # 真實 market crash (武漢/2021台疫/2024日銀/2025關稅) margin 跟 TWII 同跌, 不算 bug
    print()
    print("=" * 60)
    print("5. Margin jump > 5% but TWII jump < 3% (= 不是 market crash)")
    print("=" * 60)
    # Build TWII map for cross-check
    twii_map = {r["date"]: r["twii_close"] for r in rows}
    margin_jumps = 0
    for i in range(1, len(rows4)):
        prev = rows4[i - 1]["twse_margin_amt_oku"]
        cur = rows4[i]["twse_margin_amt_oku"]
        if not (prev and cur and abs(cur - prev) / prev > 0.05):
            continue
        # Cross-check TWII change same day
        prev_tw = twii_map.get(rows4[i - 1]["date"])
        cur_tw = twii_map.get(rows4[i]["date"])
        if prev_tw and cur_tw:
            twii_chg = abs(cur_tw - prev_tw) / prev_tw
            if twii_chg < 0.03:
                # margin big but TWII flat → real outlier
                print(f"  XX {rows4[i]['date']}: margin {prev:.2f}→{cur:.2f}億 ({(cur-prev)/prev*100:+.1f}%) TWII {prev_tw:.0f}→{cur_tw:.0f} ({(cur_tw-prev_tw)/prev_tw*100:+.1f}%)")
                margin_jumps += 1
                issues.append(("margin_jump", rows4[i]["date"], prev, cur))
    print(f"margin jumps (suspicious, not market crash): {margin_jumps}")

    print()
    print("=" * 60)
    print(f"TOTAL ISSUES: {len(issues)}")
    print("=" * 60)
    return issues


if __name__ == "__main__":
    main()
