"""Research: 法人 op_cp_net + op_legal_net (台指期等效大台 OI 淨) 對加權指數
forward return 的預測力.

問題:
1. 兩者都極端負 → 後續會跌嗎?
2. 兩者都極端正 → 後續會漲嗎?
3. 分歧 (cp 看空 fut 看多 / 反之) → 中性?
4. 量級不對稱 (|cp| > |fut| 或 反過來) → 哪個主導?
5. 持續性 (5 日平均 都極端) vs 單日極端 — 哪個更有 signal?

輸出: docs/RESEARCH_cp_fut.md (markdown report 含 conditional stats tables)
"""
import sqlite3
import statistics as st
from pathlib import Path

DB = Path(__file__).resolve().parent.parent / "data" / "data.db"
OUT = Path(__file__).resolve().parent.parent / "docs" / "RESEARCH_cp_fut.md"

HORIZONS = [1, 5, 10, 20]
ZTHRESH = 1.5  # 「極端」 = z-score 絕對值 > 1.5 (= 約 top/bottom 7%)


def pearson(xs, ys):
    n = len(xs)
    if n < 3:
        return None
    mx = sum(xs) / n
    my = sum(ys) / n
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    dx = sum((x - mx) ** 2 for x in xs)
    dy = sum((y - my) ** 2 for y in ys)
    if dx <= 0 or dy <= 0:
        return None
    return num / (dx * dy) ** 0.5


def t_test_one_sample(samples, baseline_mean):
    """Welch-ish: 是否 sample mean 顯著不等於 baseline_mean (= overall mean)?
    返 t-stat 跟 absolute 差距 / std. n>30 時 |t| > 2 視為 significant."""
    n = len(samples)
    if n < 3:
        return None, None
    s_mean = st.mean(samples)
    s_std = st.stdev(samples)
    if s_std == 0:
        return None, s_mean - baseline_mean
    se = s_std / (n ** 0.5)
    t = (s_mean - baseline_mean) / se
    return t, s_mean - baseline_mean


def rolling_mean(arr, win):
    n = len(arr)
    out = [None] * n
    for i in range(win - 1, n):
        seg = arr[i - win + 1: i + 1]
        if any(v is None for v in seg):
            continue
        out[i] = sum(seg) / win
    return out


def main():
    con = sqlite3.connect(DB)
    rows = list(con.execute(
        "SELECT date, op_cp_net, op_legal_net, twii_close "
        "FROM daily_summary "
        "WHERE op_cp_net IS NOT NULL AND op_legal_net IS NOT NULL "
        "AND twii_close IS NOT NULL ORDER BY date"
    ))
    n = len(rows)
    dates = [r[0] for r in rows]
    cp = [r[1] for r in rows]
    fut = [r[2] for r in rows]   # op_legal_net = 等效大台 OI 淨
    twii = [r[3] for r in rows]

    # --- forward returns ---
    def fwd(h):
        out = [None] * n
        for i in range(n - h):
            if twii[i] is None or twii[i + h] is None:
                continue
            out[i] = (twii[i + h] / twii[i] - 1) * 100
        return out
    rets = {h: fwd(h) for h in HORIZONS}
    daily_pct = [None] + [(twii[i] / twii[i - 1] - 1) * 100 if twii[i - 1] else None
                          for i in range(1, n)]

    # --- z-scores (= mean 0, std 1) ---
    def zscore(arr):
        vals = [v for v in arr if v is not None]
        m = st.mean(vals)
        s = st.stdev(vals)
        return [(v - m) / s if v is not None else None for v in arr]
    cp_z = zscore(cp)
    fut_z = zscore(fut)
    cp5d = rolling_mean(cp, 5)
    fut5d = rolling_mean(fut, 5)
    cp5d_z = zscore(cp5d)
    fut5d_z = zscore(fut5d)

    lines = []
    p = lines.append

    p("# Research: 法人 CP + 大台 OI 淨 對加權指數預測力")
    p("")
    p(f"資料: `daily_summary`, 範圍 {dates[0]} ~ {dates[-1]}, n = {n}")
    p("")
    p("**變數定義**:")
    p("- `cp` = `op_cp_net` = 法人選擇權 CALL net OI − PUT net OI (外資+自營商)")
    p("- `fut` = `op_legal_net` = 台指期等效大台 OI 淨 (大台 + 小台/4 + 微台/20, 外資+自營商)")
    p("- `cp5d` / `fut5d` = 5 日 rolling 平均 (看持續性)")
    p("- `r{N}` = 加權指數 T 收盤 → T+N 收盤 累計漲跌% (forward return)")
    p(f"- 「極端」定義: |z-score| > {ZTHRESH} (≈ top/bottom 7%)")
    p("")

    # --- Section 0: 變數本身敘統 ---
    p("## 0. 變數敘統")
    p("")
    p("| 變數 | min | mean | median | max | std |")
    p("|---|---:|---:|---:|---:|---:|")
    for label, arr in [("cp", cp), ("fut", fut), ("cp5d", [v for v in cp5d if v is not None]),
                        ("fut5d", [v for v in fut5d if v is not None])]:
        a = [v for v in arr if v is not None]
        p(f"| {label} | {min(a):.0f} | {st.mean(a):+.0f} | {st.median(a):+.0f} | "
          f"{max(a):.0f} | {st.stdev(a):.0f} |")
    p("")

    # --- Section 1: baseline forward return ---
    p("## 1. Baseline forward return (全段, 不條件)")
    p("")
    p("| Horizon | n | mean | median | std | win rate (>0) |")
    p("|---|---:|---:|---:|---:|---:|")
    baseline = {}
    for h in HORIZONS:
        rs = [v for v in rets[h] if v is not None]
        win = sum(1 for v in rs if v > 0) / len(rs) * 100
        baseline[h] = {"mean": st.mean(rs), "median": st.median(rs),
                        "std": st.stdev(rs), "n": len(rs), "win": win}
        p(f"| T+{h} | {len(rs)} | {st.mean(rs):+.3f}% | {st.median(rs):+.3f}% | "
          f"{st.stdev(rs):.3f}% | {win:.1f}% |")
    p("")
    p(f"_(基準: TWII T+1 baseline mean = {baseline[1]['mean']:+.3f}%/天 = annualized "
      f"~ {baseline[1]['mean'] * 252:+.1f}%/年, win rate {baseline[1]['win']:.1f}%)_")
    p("")

    # --- Section 2: 單變量 correlation ---
    p("## 2. 單變量 Pearson r (cp / fut / cp5d / fut5d vs forward returns)")
    p("")
    p("| 變數 | T+1 r | T+5 r | T+10 r | T+20 r |")
    p("|---|---:|---:|---:|---:|")
    for label, arr in [("cp", cp), ("fut", fut), ("cp5d", cp5d), ("fut5d", fut5d)]:
        cells = []
        for h in HORIZONS:
            xy = [(arr[i], rets[h][i]) for i in range(n) if arr[i] is not None and rets[h][i] is not None]
            if not xy:
                cells.append("—")
                continue
            xs, ys = zip(*xy)
            r = pearson(list(xs), list(ys))
            cells.append(f"{r:+.3f}" if r is not None else "—")
        p(f"| {label} | {' | '.join(cells)} |")
    # also add cp T0 (= same-day) — 對比
    p(f"")
    cp_same = [(cp[i], daily_pct[i]) for i in range(1, n) if cp[i] is not None and daily_pct[i] is not None]
    fut_same = [(fut[i], daily_pct[i]) for i in range(1, n) if fut[i] is not None and daily_pct[i] is not None]
    cp_r0 = pearson([x[0] for x in cp_same], [x[1] for x in cp_same])
    fut_r0 = pearson([x[0] for x in fut_same], [x[1] for x in fut_same])
    p(f"_(同期 T 漲跌: cp r = {cp_r0:+.3f}, fut r = {fut_r0:+.3f})_")
    p("")

    # --- Section 3: 兩變量 conjunction (用戶 hypothesis) ---
    p("## 3. 兩變量 conjunction — 用戶問: 兩個都極端負/正 → forward return?")
    p("")
    p(f"條件分組 (用 z-score, 閾值 ±{ZTHRESH}):")
    p("- BOTH_NEG: `cp_z < -1.5 AND fut_z < -1.5` (兩者都極端看空)")
    p("- BOTH_POS: `cp_z > +1.5 AND fut_z > +1.5` (兩者都極端看多)")
    p("- DIVERGE_CP_NEG: `cp_z < -1 AND fut_z > +1` (cp 看空, fut 看多)")
    p("- DIVERGE_CP_POS: `cp_z > +1 AND fut_z < -1` (cp 看多, fut 看空)")
    p("- NEUTRAL: |cp_z| < 0.5 AND |fut_z| < 0.5 (兩者都中性)")
    p("")

    def gather_subset(condition_fn):
        idxs = [i for i in range(n) if condition_fn(i)]
        return idxs

    conditions = [
        ("BOTH_NEG (兩者都極端看空)",
         lambda i: cp_z[i] is not None and fut_z[i] is not None and cp_z[i] < -ZTHRESH and fut_z[i] < -ZTHRESH),
        ("BOTH_POS (兩者都極端看多)",
         lambda i: cp_z[i] is not None and fut_z[i] is not None and cp_z[i] > +ZTHRESH and fut_z[i] > +ZTHRESH),
        ("DIVERGE_CP_NEG (cp 空 fut 多)",
         lambda i: cp_z[i] is not None and fut_z[i] is not None and cp_z[i] < -1 and fut_z[i] > +1),
        ("DIVERGE_CP_POS (cp 多 fut 空)",
         lambda i: cp_z[i] is not None and fut_z[i] is not None and cp_z[i] > +1 and fut_z[i] < -1),
        ("NEUTRAL (兩者都中性)",
         lambda i: cp_z[i] is not None and fut_z[i] is not None and abs(cp_z[i]) < 0.5 and abs(fut_z[i]) < 0.5),
    ]

    p("| 條件 | n | T+1 mean (vs baseline) | T+5 mean (vs base) | T+10 mean (vs base) | T+20 mean (vs base) |")
    p("|---|---:|---:|---:|---:|---:|")
    for name, fn in conditions:
        idxs = gather_subset(fn)
        cells = [f"{len(idxs)}"]
        for h in HORIZONS:
            sub = [rets[h][i] for i in idxs if rets[h][i] is not None]
            if len(sub) < 5:
                cells.append("—")
                continue
            m = st.mean(sub)
            t, diff = t_test_one_sample(sub, baseline[h]["mean"])
            sig = ""
            if t is not None and abs(t) > 2:
                sig = " **" + ("⬆" if diff > 0 else "⬇") + "**"
            cells.append(f"{m:+.3f}% ({diff:+.3f}{sig})")
        p("| " + " | ".join([name] + cells) + " |")
    p("")
    p("_(`**⬆**`/`**⬇**` = 跟 baseline 差異 |t| > 2, 統計顯著. n<5 → 樣本太少不報)_")
    p("")

    # --- Section 4: 5d rolling persistence (用戶: 「持續一段時間」) ---
    p("## 4. 持續性 — 5 日平均都極端 vs 單日極端")
    p("")
    p("用戶問: 「一段時間如果法人 CP 都是負數很大」 → 用 5 日平均 z-score 替代")
    p("")
    p("| 條件 | n | T+5 mean (vs base) | T+10 mean (vs base) | T+20 mean (vs base) |")
    p("|---|---:|---:|---:|---:|")
    persist_conds = [
        ("cp5d 極端負 (z < -1.5)",
         lambda i: cp5d_z[i] is not None and cp5d_z[i] < -ZTHRESH),
        ("fut5d 極端負 (z < -1.5)",
         lambda i: fut5d_z[i] is not None and fut5d_z[i] < -ZTHRESH),
        ("BOTH 5d 都極端負",
         lambda i: cp5d_z[i] is not None and fut5d_z[i] is not None and cp5d_z[i] < -ZTHRESH and fut5d_z[i] < -ZTHRESH),
        ("BOTH 5d 都極端正",
         lambda i: cp5d_z[i] is not None and fut5d_z[i] is not None and cp5d_z[i] > +ZTHRESH and fut5d_z[i] > +ZTHRESH),
    ]
    for name, fn in persist_conds:
        idxs = gather_subset(fn)
        cells = [f"{len(idxs)}"]
        for h in [5, 10, 20]:
            sub = [rets[h][i] for i in idxs if rets[h][i] is not None]
            if len(sub) < 5:
                cells.append("—")
                continue
            m = st.mean(sub)
            t, diff = t_test_one_sample(sub, baseline[h]["mean"])
            sig = ""
            if t is not None and abs(t) > 2:
                sig = " **" + ("⬆" if diff > 0 else "⬇") + "**"
            cells.append(f"{m:+.3f}% ({diff:+.3f}{sig})")
        p("| " + " | ".join([name] + cells) + " |")
    p("")

    # --- Section 5: 量級不對稱 ---
    p("## 5. 量級不對稱 — |cp_z| vs |fut_z| 哪個 dominates")
    p("")

    asym_conds = [
        ("|cp_z|>1 且 cp_z 跟 fut_z 同號 但 |cp_z| > |fut_z| (cp 較極端)",
         lambda i: cp_z[i] is not None and fut_z[i] is not None
                   and abs(cp_z[i]) > 1 and (cp_z[i] * fut_z[i] > 0)
                   and abs(cp_z[i]) > abs(fut_z[i])),
        ("|fut_z|>1 且 同號 但 |fut_z| > |cp_z| (fut 較極端)",
         lambda i: cp_z[i] is not None and fut_z[i] is not None
                   and abs(fut_z[i]) > 1 and (cp_z[i] * fut_z[i] > 0)
                   and abs(fut_z[i]) > abs(cp_z[i])),
    ]
    p("| 條件 | n | sign | T+5 mean (vs base) | T+20 mean (vs base) |")
    p("|---|---:|---:|---:|---:|")
    for name, fn in asym_conds:
        idxs = gather_subset(fn)
        if not idxs:
            p(f"| {name} | 0 | — | — | — |")
            continue
        # split by sign of dominant variable
        pos_i = [i for i in idxs if (cp_z[i] + fut_z[i]) > 0]
        neg_i = [i for i in idxs if (cp_z[i] + fut_z[i]) < 0]
        for sign_label, sub_i in [("正向", pos_i), ("負向", neg_i)]:
            if len(sub_i) < 5:
                continue
            cells = [f"{len(sub_i)}", sign_label]
            for h in [5, 20]:
                sub = [rets[h][i] for i in sub_i if rets[h][i] is not None]
                if len(sub) < 5:
                    cells.append("—")
                    continue
                m = st.mean(sub)
                t, diff = t_test_one_sample(sub, baseline[h]["mean"])
                sig = ""
                if t is not None and abs(t) > 2:
                    sig = " **" + ("⬆" if diff > 0 else "⬇") + "**"
                cells.append(f"{m:+.3f}% ({diff:+.3f}{sig})")
            p("| " + " | ".join([name] + cells) + " |")
    p("")

    # --- Section 6: 結論 ---
    p("## 6. 自我研究結論 (不是用戶交代的, 是我從數字看出的)")
    p("")
    p("待 fill — 在 main() 跑完後我看 output 再寫")
    p("")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(lines), encoding="utf-8")
    print(f"Written: {OUT}")
    print(f"Lines: {len(lines)}")


if __name__ == "__main__":
    main()
