"""Research 台指期法人淨部位 vs 台指期點位.

Focus:
  - main signal: daily_summary.op_legal_net
    (台指期大台等效 OI 淨部位: 大台 + 小台/4 + 微台/20, 外資 + 自營商)
  - reference price: daily_summary.tx_close
  - forward return: TX close from T to T+N trading days

The report intentionally uses walk-forward z-scores where possible, so the
threshold does not know the future distribution.
"""
from __future__ import annotations

import math
import random
import sqlite3
import statistics as st
from collections import Counter
from pathlib import Path

DB = Path(__file__).resolve().parent.parent / "data" / "data.db"
OUT = Path(__file__).resolve().parent.parent / "docs" / "RESEARCH_tx_fut_net_vs_price.md"
HORIZONS = [1, 3, 5, 10, 20]
random.seed(20260508)


def pearson(xs: list[float], ys: list[float]) -> float | None:
    if len(xs) < 3:
        return None
    mx, my = st.mean(xs), st.mean(ys)
    sx = sum((x - mx) ** 2 for x in xs)
    sy = sum((y - my) ** 2 for y in ys)
    if sx <= 0 or sy <= 0:
        return None
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / math.sqrt(sx * sy)


def rolling_mean(vals: list[float | None], win: int) -> list[float | None]:
    out: list[float | None] = [None] * len(vals)
    for i in range(win - 1, len(vals)):
        seg = vals[i - win + 1 : i + 1]
        if any(v is None for v in seg):
            continue
        out[i] = sum(v for v in seg if v is not None) / win
    return out


def walk_forward_z(vals: list[float | None], win: int = 252) -> list[float | None]:
    out: list[float | None] = [None] * len(vals)
    for i in range(win, len(vals)):
        hist = [v for v in vals[i - win : i] if v is not None]
        if len(hist) < max(60, win // 2) or vals[i] is None:
            continue
        sd = st.stdev(hist)
        if sd == 0:
            continue
        out[i] = (vals[i] - st.mean(hist)) / sd
    return out


def forward_returns(px: list[float | None], h: int) -> list[float | None]:
    out: list[float | None] = [None] * len(px)
    for i in range(len(px) - h):
        if px[i] is None or px[i + h] is None:
            continue
        out[i] = (px[i + h] / px[i] - 1) * 100
    return out


def same_day_returns(px: list[float | None]) -> list[float | None]:
    out: list[float | None] = [None] * len(px)
    for i in range(1, len(px)):
        if px[i - 1] is None or px[i] is None:
            continue
        out[i] = (px[i] / px[i - 1] - 1) * 100
    return out


def bootstrap_ci(samples: list[float], n_boot: int = 3000) -> tuple[float, float]:
    if len(samples) < 5:
        return (float("nan"), float("nan"))
    means = []
    n = len(samples)
    for _ in range(n_boot):
        means.append(sum(samples[random.randrange(n)] for _ in range(n)) / n)
    means.sort()
    return means[int(n_boot * 0.025)], means[int(n_boot * 0.975) - 1]


def run_lengths(mask: list[bool]) -> list[int]:
    out = [0] * len(mask)
    cur = 0
    for i, ok in enumerate(mask):
        cur = cur + 1 if ok else 0
        out[i] = cur
    return out


def fmt_pct(x: float | None) -> str:
    return "NA" if x is None or math.isnan(x) else f"{x:+.3f}%"


def summarize_condition(
    name: str,
    idxs: list[int],
    rets: dict[int, list[float | None]],
    baseline: dict[int, float],
) -> list[str]:
    lines = []
    cells = [name, str(len(idxs))]
    for h in HORIZONS:
        vals = [rets[h][i] for i in idxs if rets[h][i] is not None]
        if len(vals) < 8:
            cells.append("樣本不足")
            continue
        mean = st.mean(vals)
        diff = mean - baseline[h]
        win = sum(v > 0 for v in vals) / len(vals) * 100
        lo, hi = bootstrap_ci(vals)
        cells.append(f"{mean:+.3f}% ({diff:+.3f}, 勝率 {win:.1f}%, CI {lo:+.2f}~{hi:+.2f})")
    lines.append("| " + " | ".join(cells) + " |")
    return lines


def main() -> None:
    con = sqlite3.connect(DB)
    rows = list(con.execute(
        """
        SELECT date, op_legal_net, fut_pre_open_net, tx_close
        FROM daily_summary
        WHERE op_legal_net IS NOT NULL AND tx_close IS NOT NULL
        ORDER BY date
        """
    ))
    dates = [r[0] for r in rows]
    fut = [float(r[1]) if r[1] is not None else None for r in rows]
    preopen = [float(r[2]) if r[2] is not None else None for r in rows]
    tx = [float(r[3]) if r[3] is not None else None for r in rows]
    n = len(rows)

    rets = {h: forward_returns(tx, h) for h in HORIZONS}
    ret0 = same_day_returns(tx)
    fut5 = rolling_mean(fut, 5)
    fut10 = rolling_mean(fut, 10)
    z = walk_forward_z(fut, 252)
    z5 = walk_forward_z(fut5, 252)
    z10 = walk_forward_z(fut10, 252)
    neg_run = run_lengths([v is not None and v < 0 for v in fut])
    extreme_neg_run = run_lengths([v is not None and v < -1.5 for v in z])

    baseline = {h: st.mean([v for v in rets[h] if v is not None]) for h in HORIZONS}
    baseline_win = {
        h: sum(v > 0 for v in rets[h] if v is not None) / len([v for v in rets[h] if v is not None]) * 100
        for h in HORIZONS
    }

    lines: list[str] = []
    p = lines.append
    p("# 台指期法人淨部位 vs 台指期點位研究")
    p("")
    p(f"資料: `daily_summary`, {dates[0]} ~ {dates[-1]}, n={n} 個交易日。")
    p("")
    p("定義:")
    p("- `台指期法人淨部位` = `op_legal_net`，台指期大台等效 OI 淨部位，大台 + 小台/4 + 微台/20，外資 + 自營商。")
    p("- `台指期點位` = `tx_close`，台指期近月收盤。")
    p("- `T+N報酬` = 從 T 收盤到 T+N 交易日收盤的台指期累計報酬。")
    p("- 極端門檻用 walk-forward 252 日 z-score，避免用未來資料決定當下是否極端。")
    p("")

    fut_vals = [v for v in fut if v is not None]
    pre_vals = [v for v in preopen if v is not None]
    p("## 1. 敘述統計")
    p("")
    p("| 變數 | min | mean | median | max | std |")
    p("|---|---:|---:|---:|---:|---:|")
    p(f"| op_legal_net | {min(fut_vals):.0f} | {st.mean(fut_vals):+.0f} | {st.median(fut_vals):+.0f} | {max(fut_vals):.0f} | {st.stdev(fut_vals):.0f} |")
    p(f"| fut_pre_open_net | {min(pre_vals):.0f} | {st.mean(pre_vals):+.0f} | {st.median(pre_vals):+.0f} | {max(pre_vals):.0f} | {st.stdev(pre_vals):.0f} |")
    p("")

    p("## 2. 相關係數")
    p("")
    p("| X | Y | n | Pearson r |")
    p("|---|---|---:|---:|")
    pairs = [(fut[i], tx[i]) for i in range(n) if fut[i] is not None and tx[i] is not None]
    p(f"| 法人淨部位 | 台指期點位 | {len(pairs)} | {pearson([x for x, _ in pairs], [y for _, y in pairs]):+.3f} |")
    pairs = [(fut[i], ret0[i]) for i in range(n) if fut[i] is not None and ret0[i] is not None]
    p(f"| 法人淨部位 | 同日報酬 | {len(pairs)} | {pearson([x for x, _ in pairs], [y for _, y in pairs]):+.3f} |")
    p("")
    p("| X | T+1 r | T+3 r | T+5 r | T+10 r | T+20 r |")
    p("|---|---:|---:|---:|---:|---:|")
    for label, arr in [("當日淨部位", fut), ("5日平均", fut5), ("10日平均", fut10), ("walk-forward z", z)]:
        row = [label]
        for h in HORIZONS:
            pairs = [(arr[i], rets[h][i]) for i in range(n) if arr[i] is not None and rets[h][i] is not None]
            r = pearson([x for x, _ in pairs], [y for _, y in pairs])
            row.append(f"{r:+.3f}" if r is not None else "NA")
        p("| " + " | ".join(row) + " |")
    p("")

    p("## 3. Baseline")
    p("")
    p("| Horizon | mean | median | std | win rate |")
    p("|---|---:|---:|---:|---:|")
    for h in HORIZONS:
        vals = [v for v in rets[h] if v is not None]
        p(f"| T+{h} | {st.mean(vals):+.3f}% | {st.median(vals):+.3f}% | {st.stdev(vals):.3f}% | {baseline_win[h]:.1f}% |")
    p("")

    p("## 4. 法人淨部位負很大，對未來 N 天的影響")
    p("")
    p("表格每格: 條件內平均報酬（相對 baseline 差異、勝率、bootstrap 95% CI）。")
    p("")
    p("| 條件 | n | T+1 | T+3 | T+5 | T+10 | T+20 |")
    p("|---|---:|---:|---:|---:|---:|---:|")
    conditions = [
        ("z < -1.0", [i for i, v in enumerate(z) if v is not None and v < -1.0]),
        ("z < -1.5", [i for i, v in enumerate(z) if v is not None and v < -1.5]),
        ("z < -2.0", [i for i, v in enumerate(z) if v is not None and v < -2.0]),
        ("5日均 z < -1.5", [i for i, v in enumerate(z5) if v is not None and v < -1.5]),
        ("10日均 z < -1.5", [i for i, v in enumerate(z10) if v is not None and v < -1.5]),
        ("淨空連續 >=5日", [i for i, v in enumerate(neg_run) if v >= 5]),
        ("淨空連續 >=20日", [i for i, v in enumerate(neg_run) if v >= 20]),
        ("極端淨空連續 >=3日", [i for i, v in enumerate(extreme_neg_run) if v >= 3]),
    ]
    for name, idxs in conditions:
        lines.extend(summarize_condition(name, idxs, rets, baseline))
    p("")

    p("## 5. 正負兩端比較")
    p("")
    p("| 條件 | n | T+1 | T+3 | T+5 | T+10 | T+20 |")
    p("|---|---:|---:|---:|---:|---:|---:|")
    for name, idxs in [
        ("z > +1.5", [i for i, v in enumerate(z) if v is not None and v > 1.5]),
        ("z < -1.5", [i for i, v in enumerate(z) if v is not None and v < -1.5]),
        ("5日均 z > +1.5", [i for i, v in enumerate(z5) if v is not None and v > 1.5]),
        ("5日均 z < -1.5", [i for i, v in enumerate(z5) if v is not None and v < -1.5]),
    ]:
        lines.extend(summarize_condition(name, idxs, rets, baseline))
    p("")

    p("## 6. 累積天數分布")
    p("")
    neg_lengths = Counter()
    cur = 0
    for ok in [v is not None and v < 0 for v in fut] + [False]:
        if ok:
            cur += 1
        elif cur:
            neg_lengths[cur] += 1
            cur = 0
    p("| 淨空連續區間 | 發生段數 |")
    p("|---|---:|")
    buckets = {
        "1-4日": sum(c for k, c in neg_lengths.items() if 1 <= k <= 4),
        "5-9日": sum(c for k, c in neg_lengths.items() if 5 <= k <= 9),
        "10-19日": sum(c for k, c in neg_lengths.items() if 10 <= k <= 19),
        "20-39日": sum(c for k, c in neg_lengths.items() if 20 <= k <= 39),
        "40日以上": sum(c for k, c in neg_lengths.items() if k >= 40),
    }
    for k, c in buckets.items():
        p(f"| {k} | {c} |")
    longest = max(neg_lengths) if neg_lengths else 0
    longest_ends = [dates[i] for i, v in enumerate(neg_run) if v == longest]
    p("")
    p(f"最長連續淨空: {longest} 個交易日，結束日: {', '.join(longest_ends[:5])}")
    p("")

    p("## 7. 結論")
    p("")
    p("1. 同張走勢圖適合用來看 regime：法人淨部位與台指期點位同向程度不穩定，長週期下會看到部位跟價格同時抬升或同時下滑，但這不等於可預測。")
    p("2. 單看法人淨部位對未來 1、3、5、10、20 日台指期報酬的線性相關，多數接近 0；預測力弱。")
    p("3. 「法人淨部位負很大」不是穩定的看空訊號。用 walk-forward z<-1.5 或 5/10 日均線極端淨空測試，平均報酬有時偏正，較像反向/擁擠部位解除訊號，但信賴區間通常寬，不能當單一交易規則。")
    p("4. 「累積很多日都是淨空」本身也不夠。連續淨空 >=20 日的樣本不少，但未來報酬沒有單調變差；更像描述市場處於某個風格，而不是精準 timing。")
    p("5. 實務上較好的用法：把 z-score < -1.5 且持續 5-10 日視為風險狀態標記，再搭配價格趨勢、期現價差、波動與選擇權 CP。不要只因法人淨空很大就推論未來必跌。")

    OUT.write_text("\n".join(lines), encoding="utf-8")
    print(f"written {OUT}")


if __name__ == "__main__":
    main()
