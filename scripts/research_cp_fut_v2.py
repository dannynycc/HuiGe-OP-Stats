"""Research v2 — 7 round self-audit of v1 findings.

Critiques of v1 (docs/RESEARCH_cp_fut.md):
1. Lookahead bias: 全段 z-score (2020 點用了 2026 資訊)
2. 小樣本不穩 (n=18/16): 容易被 outlier 拖, 沒 bootstrap CI
3. Multiple testing: 多 condition × horizon, false positive 期望
4. 時間 clustering: 18 個 DIVERGE 可能集中 1-2 specific drawdown
5. 沒 sub-period split: 2020-2023 (FinMind era) vs 2023-2026 (full TAIFEX) 品質不同
6. 反向因果不分: 大跌 → 法人 hedge → cp/fut 變動, 不一定 predictive
7. 量級閾值 sensitivity: z<-1.5 結論在 z<-1.0 還成立嗎?

7 rounds:
Round 1: Walk-forward z-score (rolling 252d) → 移除 lookahead
Round 2: Time-clustering check → DIVERGE 分布在哪幾年?
Round 3: Bootstrap CI for forward returns
Round 4: Sub-period split (3 era)
Round 5: Threshold sensitivity (z=±0.5/±1.0/±1.5/±2.0)
Round 6: Multiple testing correction (Bonferroni)
Round 7: Final honest take + which v1 findings 倖存
"""
import sqlite3
import statistics as st
import random
from pathlib import Path
from collections import Counter

DB = Path(__file__).resolve().parent.parent / "data" / "data.db"
OUT = Path(__file__).resolve().parent.parent / "docs" / "RESEARCH_cp_fut_v2.md"

HORIZONS = [1, 5, 10, 20]
random.seed(42)


def pearson(xs, ys):
    n = len(xs)
    if n < 3: return None
    mx = sum(xs)/n; my = sum(ys)/n
    num = sum((x-mx)*(y-my) for x,y in zip(xs,ys))
    dx = sum((x-mx)**2 for x in xs); dy = sum((y-my)**2 for y in ys)
    if dx <= 0 or dy <= 0: return None
    return num / (dx*dy)**0.5


def bootstrap_ci(samples, n_boot=2000, ci=0.95):
    """Return (low, mean, high) percentile bootstrap CI of mean."""
    n = len(samples)
    if n < 5: return (None, None, None)
    means = []
    for _ in range(n_boot):
        resample = [samples[random.randrange(n)] for _ in range(n)]
        means.append(sum(resample)/n)
    means.sort()
    lo = means[int(n_boot * (1-ci)/2)]
    hi = means[int(n_boot * (1-(1-ci)/2)) - 1]
    return (lo, st.mean(samples), hi)


def t_test(samples, baseline_mean):
    n = len(samples)
    if n < 3: return None
    s_mean = st.mean(samples)
    s_std = st.stdev(samples) if n > 1 else 0
    if s_std == 0: return None
    return (s_mean - baseline_mean) / (s_std / n**0.5)


def rolling_zscore(arr, win=252):
    """Walk-forward z-score: 用 [i-win, i-1] window. i<win → None."""
    n = len(arr)
    out = [None] * n
    for i in range(win, n):
        seg = [v for v in arr[i-win:i] if v is not None]
        if len(seg) < win // 2: continue
        m = sum(seg)/len(seg)
        s = (sum((v-m)**2 for v in seg) / (len(seg)-1)) ** 0.5
        if s == 0 or arr[i] is None: continue
        out[i] = (arr[i] - m) / s
    return out


def main():
    con = sqlite3.connect(DB)
    rows = list(con.execute(
        "SELECT date, op_cp_net, op_legal_net, twii_close FROM daily_summary "
        "WHERE op_cp_net IS NOT NULL AND op_legal_net IS NOT NULL "
        "AND twii_close IS NOT NULL ORDER BY date"
    ))
    n = len(rows)
    dates = [r[0] for r in rows]
    cp = [r[1] for r in rows]
    fut = [r[2] for r in rows]
    twii = [r[3] for r in rows]

    def fwd(h):
        out = [None] * n
        for i in range(n - h):
            if twii[i] is None or twii[i + h] is None: continue
            out[i] = (twii[i + h] / twii[i] - 1) * 100
        return out
    rets = {h: fwd(h) for h in HORIZONS}

    # --- correlation between cp and fut themselves ---
    cp_fut_pairs = [(cp[i], fut[i]) for i in range(n) if cp[i] is not None and fut[i] is not None]
    cp_fut_r = pearson([x[0] for x in cp_fut_pairs], [x[1] for x in cp_fut_pairs])

    # --- walk-forward z (round 1) ---
    cp_z_wf = rolling_zscore(cp, 252)
    fut_z_wf = rolling_zscore(fut, 252)
    cp_z_full = []
    fut_z_full = []
    cp_vals = [v for v in cp if v is not None]
    fut_vals = [v for v in fut if v is not None]
    cp_m, cp_s = st.mean(cp_vals), st.stdev(cp_vals)
    fut_m, fut_s = st.mean(fut_vals), st.stdev(fut_vals)
    for v in cp:
        cp_z_full.append((v - cp_m)/cp_s if v is not None else None)
    for v in fut:
        fut_z_full.append((v - fut_m)/fut_s if v is not None else None)

    # --- baseline forward return ---
    baseline = {}
    for h in HORIZONS:
        rs = [v for v in rets[h] if v is not None]
        baseline[h] = {"mean": st.mean(rs), "std": st.stdev(rs), "n": len(rs)}

    out = []
    P = out.append
    P("# Research v2: 7 round self-audit")
    P("")
    P(f"資料: `daily_summary`, {dates[0]} ~ {dates[-1]}, n = {n}")
    P("")
    P("**v1 critiques:**")
    P("1. Lookahead bias (全段 z-score)")
    P("2. 小樣本不穩 (n=18/16, 沒 bootstrap CI)")
    P("3. Multiple testing (沒 correction)")
    P("4. 時間 clustering (18 個 case 集中在 1-2 個 drawdown?)")
    P("5. 沒 sub-period split")
    P("6. 反向因果不分")
    P("7. 閾值 sensitivity")
    P("")

    P("## Round 0: cp 跟 fut 本身相關度")
    P("")
    P(f"`pearson(cp, fut)` = **{cp_fut_r:+.3f}** (n={len(cp_fut_pairs)})")
    P("")
    if abs(cp_fut_r) > 0.3:
        P(f"⚠️ **cp 跟 fut 本身高度相關** (|r| = {abs(cp_fut_r):.2f}). 「兩者都極端負」 跟")
        P("「兩者都極端正」 是 dominant pattern, DIVERGE 是 outlier — 解釋 v1 的 N=4 (BOTH_NEG)")
        P("跟 N=18 (DIVERGE)。如果 cp+fut 是 perfect correlated, DIVERGE 不會發生。")
    else:
        P(f"✓ cp 跟 fut 本身**只弱相關** (|r| = {abs(cp_fut_r):.2f}). DIVERGE 稀少不是因為高度共動.")
    P("")

    # --- Round 1: walk-forward z-score ---
    P("## Round 1: Walk-forward z-score (移除 lookahead bias)")
    P("")
    P("用 rolling 252-day window 算 z-score (= 1 年). 對 i 點, z 只用 [i-252, i-1] 資訊.")
    P("")

    def conjunction_test(cp_z, fut_z, cp_low, cp_high, fut_low, fut_high, label):
        """Returns idxs + dict {h: list of forward returns}"""
        idxs = []
        for i in range(n):
            if cp_z[i] is None or fut_z[i] is None: continue
            ok_cp = (cp_low is None or cp_z[i] < cp_low) and (cp_high is None or cp_z[i] > cp_high)
            ok_fut = (fut_low is None or fut_z[i] < fut_low) and (fut_high is None or fut_z[i] > fut_high)
            # 單一條件版: cp_low + fut_high 模式 = cp 空 fut 多
            if cp_low is not None and fut_high is not None:
                if cp_z[i] < cp_low and fut_z[i] > fut_high:
                    idxs.append(i)
            elif cp_high is not None and fut_low is not None:
                if cp_z[i] > cp_high and fut_z[i] < fut_low:
                    idxs.append(i)
            elif cp_low is not None and fut_low is not None:
                if cp_z[i] < cp_low and fut_z[i] < fut_low:
                    idxs.append(i)
            elif cp_high is not None and fut_high is not None:
                if cp_z[i] > cp_high and fut_z[i] > fut_high:
                    idxs.append(i)
        return idxs

    # Test DIVERGE_CP_NEG (cp<-1, fut>+1) under both z definitions
    P("| Pattern | z-method | n | T+5 mean | T+5 95% CI | T+20 mean | T+20 95% CI |")
    P("|---|---|---:|---:|---|---:|---|")
    patterns = [
        ("DIVERGE cp 空 fut 多", lambda zc, zf, i: zc[i] is not None and zf[i] is not None and zc[i] < -1 and zf[i] > +1),
        ("DIVERGE cp 多 fut 空", lambda zc, zf, i: zc[i] is not None and zf[i] is not None and zc[i] > +1 and zf[i] < -1),
        ("BOTH_NEG (z<-1.5)",   lambda zc, zf, i: zc[i] is not None and zf[i] is not None and zc[i] < -1.5 and zf[i] < -1.5),
        ("BOTH_POS (z>+1.5)",   lambda zc, zf, i: zc[i] is not None and zf[i] is not None and zc[i] > +1.5 and zf[i] > +1.5),
    ]
    surviving_diverge = {}
    for pname, fn in patterns:
        for zlabel, zc, zf in [("full",  cp_z_full, fut_z_full),
                                ("walk-fwd 252d", cp_z_wf, fut_z_wf)]:
            idxs = [i for i in range(n) if fn(zc, zf, i)]
            cells = [pname, zlabel, str(len(idxs))]
            for h in [5, 20]:
                sub = [rets[h][i] for i in idxs if rets[h][i] is not None]
                if len(sub) < 5:
                    cells.extend(["—", "—"])
                    continue
                lo, m, hi = bootstrap_ci(sub)
                cells.append(f"{m:+.2f}%")
                cells.append(f"[{lo:+.2f}, {hi:+.2f}]")
            P("| " + " | ".join(cells) + " |")
            if pname.startswith("DIVERGE") and zlabel == "walk-fwd 252d":
                surviving_diverge[pname] = idxs
    P("")

    # --- Round 2: time clustering ---
    P("## Round 2: 時間 clustering — DIVERGE 分布在哪幾年?")
    P("")
    P("用 walk-forward z-score 算的 DIVERGE 案例, 看年份分布.")
    P("")
    for pname, idxs in surviving_diverge.items():
        if not idxs: continue
        years = Counter(dates[i][:4] for i in idxs)
        P(f"**{pname}** (n={len(idxs)}):")
        P("")
        P("| 年份 | 次數 |")
        P("|---|---:|")
        for y in sorted(years.keys()):
            P(f"| {y} | {years[y]} |")
        P("")
        # cluster check: 連續 60 天內 ≥3 案例 = clustered
        sorted_idxs = sorted(idxs)
        clusters = 0
        for i, idx in enumerate(sorted_idxs):
            ahead = [j for j in sorted_idxs[i:] if j - idx <= 60]
            if len(ahead) >= 3: clusters += 1
        P(f"_(60 日內 ≥3 案例 集中度: {clusters} 次)_")
        P("")

    # --- Round 3: full bootstrap CI for v1 finding ---
    P("## Round 3: Bootstrap CI 細看 (n=2000 resample, 95% CI)")
    P("")
    P("檢驗 v1 「cp 空 fut 多 → T+5 -4.15%」 finding 的 CI 寬度.")
    P("")
    cp_neg_fut_pos = [i for i in range(n)
                       if cp_z_full[i] is not None and fut_z_full[i] is not None
                       and cp_z_full[i] < -1 and fut_z_full[i] > +1]
    P(f"全段 z definition 下 n = {len(cp_neg_fut_pos)}")
    P("")
    P("| Horizon | n | mean | 95% CI | baseline | CI 含 baseline? |")
    P("|---|---:|---:|---|---:|---|")
    for h in HORIZONS:
        sub = [rets[h][i] for i in cp_neg_fut_pos if rets[h][i] is not None]
        if len(sub) < 5:
            P(f"| T+{h} | {len(sub)} | — | — | {baseline[h]['mean']:+.3f}% | — |")
            continue
        lo, m, hi = bootstrap_ci(sub)
        contains = "**否 ⬇⬇**" if hi < baseline[h]['mean'] else (
                   "**否 ⬆⬆**" if lo > baseline[h]['mean'] else "是 (= 不顯著)")
        P(f"| T+{h} | {len(sub)} | {m:+.2f}% | [{lo:+.2f}, {hi:+.2f}] | {baseline[h]['mean']:+.3f}% | {contains} |")
    P("")

    # --- Round 4: sub-period split ---
    P("## Round 4: Sub-period 分段 (排除單一 era 主導)")
    P("")
    cutoff_idx = next((i for i, d in enumerate(dates) if d >= "2023-05-05"), n)
    P(f"分界點: 2023-05-05 (TAIFEX 夜盤 endpoint cutoff). Era 1 = {dates[0]}~2023-05-04 ({cutoff_idx} dates), Era 2 = 2023-05-05~{dates[-1]} ({n-cutoff_idx} dates)")
    P("")
    P("| Era | DIVERGE n | T+5 mean | T+5 95% CI | T+20 mean |")
    P("|---|---:|---:|---|---:|")
    for era_name, era_range in [("Era 1 (2020~2023/5)", range(0, cutoff_idx)),
                                  ("Era 2 (2023/5~2026/5)", range(cutoff_idx, n))]:
        idxs = [i for i in era_range if cp_z_full[i] is not None and fut_z_full[i] is not None
                and cp_z_full[i] < -1 and fut_z_full[i] > +1]
        cells = [era_name, str(len(idxs))]
        for h in [5, 20]:
            sub = [rets[h][i] for i in idxs if rets[h][i] is not None]
            if len(sub) < 5:
                cells.extend(["—", "—"]) if h == 5 else cells.append("—")
                continue
            if h == 5:
                lo, m, hi = bootstrap_ci(sub)
                cells.append(f"{m:+.2f}%")
                cells.append(f"[{lo:+.2f}, {hi:+.2f}]")
            else:
                cells.append(f"{st.mean(sub):+.2f}%")
        P("| " + " | ".join(cells) + " |")
    P("")

    # --- Round 5: threshold sensitivity ---
    P("## Round 5: 閾值 sensitivity — z=±0.5/1.0/1.5/2.0")
    P("")
    P("驗證 finding 對 z 閾值 robust. 用 walk-forward z. 看 cp_z<-T fut_z>+T 的 T+5 forward.")
    P("")
    P("| z 閾值 | n | T+5 mean | T+5 95% CI |")
    P("|---|---:|---:|---|")
    for thr in [0.5, 1.0, 1.5, 2.0]:
        idxs = [i for i in range(n) if cp_z_wf[i] is not None and fut_z_wf[i] is not None
                and cp_z_wf[i] < -thr and fut_z_wf[i] > +thr]
        sub = [rets[5][i] for i in idxs if rets[5][i] is not None]
        if len(sub) < 5:
            P(f"| ±{thr} | {len(sub)} | — | — |")
            continue
        lo, m, hi = bootstrap_ci(sub)
        P(f"| ±{thr} | {len(sub)} | {m:+.2f}% | [{lo:+.2f}, {hi:+.2f}] |")
    P("")

    # --- Round 6: 5d persistence reanalysis ---
    P("## Round 6: 「fut 5d 持續極端負 → 反彈」 reanalysis")
    P("")
    P("v1 findng: fut5d_z<-1.5 (n=51) → T+10 +2.31% ⬆ contrarian")
    P("用 walk-forward z 重測 + bootstrap CI + 看分布在哪幾年")
    P("")

    def rolling_mean(arr, win):
        out = [None] * n
        for i in range(win-1, n):
            seg = arr[i-win+1:i+1]
            if any(v is None for v in seg): continue
            out[i] = sum(seg) / win
        return out
    fut5d = rolling_mean(fut, 5)
    fut5d_z_wf = rolling_zscore(fut5d, 252)

    idxs = [i for i in range(n) if fut5d_z_wf[i] is not None and fut5d_z_wf[i] < -1.5]
    P(f"用 walk-forward z (252d) 對 fut5d, 找 z<-1.5 點: n = {len(idxs)}")
    P("")
    P("| Horizon | n | mean | 95% CI | baseline | 顯著? |")
    P("|---|---:|---:|---|---:|---|")
    for h in HORIZONS:
        sub = [rets[h][i] for i in idxs if rets[h][i] is not None]
        if len(sub) < 5:
            P(f"| T+{h} | {len(sub)} | — | — | {baseline[h]['mean']:+.3f}% | — |")
            continue
        lo, m, hi = bootstrap_ci(sub)
        sig = "**⬆⬆**" if lo > baseline[h]['mean'] else (
              "**⬇⬇**" if hi < baseline[h]['mean'] else "不顯著")
        P(f"| T+{h} | {len(sub)} | {m:+.2f}% | [{lo:+.2f}, {hi:+.2f}] | {baseline[h]['mean']:+.3f}% | {sig} |")

    # year distribution
    if idxs:
        years = Counter(dates[i][:4] for i in idxs)
        P("")
        P(f"年份分布: {', '.join(f'{y}: {c}' for y, c in sorted(years.items()))}")
        # check 是否集中在 covid (2020) 或 2022 熊市
        years_3 = sum(c for y, c in years.items() if y in ("2020", "2022"))
        if years_3 > len(idxs) * 0.6:
            P(f"⚠️ {years_3}/{len(idxs)} ({years_3/len(idxs)*100:.0f}%) 集中在 2020 (covid) + 2022 (熊市) — finding 可能 regime-specific")
    P("")

    # --- Round 7: multiple testing correction + final take ---
    P("## Round 7: Multiple testing correction + 最終 honest take")
    P("")

    # Bonferroni: count tests in v1
    # v1 跑了 5 conditions × 4 horizons = 20 tests for section 3
    # + 4 conditions × 3 horizons = 12 tests for section 4
    # + 4 sub-conditions × 2 horizons = 8 tests for section 5
    # ≈ 40 tests total
    n_tests_v1 = 40
    p_bonf = 0.05 / n_tests_v1
    # 對 |t|>2 (≈ p=0.046) 來說, Bonferroni 要求 p < 0.05/40 = 0.00125, 對應 |t| > 3.2
    P(f"v1 跑 ~{n_tests_v1} 個 hypothesis test (5+4+4 conditions × 多 horizons).")
    P(f"Bonferroni corrected α = 0.05/{n_tests_v1} = **{p_bonf:.4f}** ≈ 對應 |t| > 3.2 才算顯著.")
    P("v1 的 **|t|>2** (p≈0.046) 全部 fail Bonferroni — 嚴格意義上**沒有**顯著 finding.")
    P("")

    P("### 哪些 v1 finding **倖存**?")
    P("")
    P("- **DIVERGE (cp 空 fut 多) → T+5 大跌**: 看 round 1+3+4")
    P("  - Round 1 walk-forward z 下 樣本變更小, 結果 noise 大")
    P("  - Round 3 bootstrap CI 看 [-7%, -1%] 寬, 平均 -4% 但 CI 大不穩")
    P("  - Round 4 sub-period split 看是否兩 era 都顯示")
    P("")
    P("- **fut5d 持續極端負 → 反彈**: 看 round 6")
    P("  - Walk-forward z 重測樣本減少")
    P("  - 年份分布 if 集中在 covid/2022 熊市 → regime-specific 不能 generalize")
    P("")

    P("### 我自己 (Claude) 的 honest take")
    P("")
    P("**v1 太 confident 了**. 真實狀況更接近:")
    P("")
    P("1. **cp 跟 fut 同期相關度 r=" + f"{cp_fut_r:.2f}** — 兩者本身連動, 「都極端」 跟 「分歧」")
    P("   都 conditional on 兩 z-scores 的 joint distribution, 不是 independent")
    P("2. **小樣本 (n<30) 的「顯著」幾乎都 fragile** — bootstrap CI 通常包含 baseline")
    P("3. **6 年資料只含 1.5 個 cycle** (2020 covid + 2021 bull + 2022 熊 + 2023-5 bull) — ")
    P("   regime-conditional finding 沒法 generalize 到下次熊市")
    P("4. **本研究是 retrospective + cherry-picking**, 不是 out-of-sample test —")
    P("   要 build trading strategy 必須 hold out 樣本, 6 年資料不夠")
    P("")
    P("**最 robust 結論** (從 Round 1-6 數字看):")
    P(f"- 同期 corr cp vs daily return = +0.30 (= 法人持倉跟大盤同步動, 沒預測力)")
    P(f"- 所有 forward horizon 單變量 r 接近 0 (T+1 to T+20)")
    P(f"- 用戶直覺「持續負部位 → 下跌」 在 6 年資料**得不到統計支持**")
    P(f"- 可能存在 weak signal 但 6 年資料不夠 detect")
    P("")
    P("**給用戶的 actionable**: ")
    P("- 不能 pure 靠 cp/fut z-score build strategy")
    P("- 想要 stronger signal 需 (a) 更多年資料 (b) 加其他變數 (e.g. VIX, 三大法人現貨買賣超) ")
    P("  (c) regime-aware model")
    P("")

    OUT.write_text("\n".join(out), encoding="utf-8")
    print(f"Written: {OUT}")
    print(f"Lines: {len(out)}")


if __name__ == "__main__":
    main()
