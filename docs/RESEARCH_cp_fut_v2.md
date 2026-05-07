# Research v2: 7 round self-audit

資料: `daily_summary`, 2020-01-02 ~ 2026-05-06, n = 1537

**v1 critiques:**
1. Lookahead bias (全段 z-score)
2. 小樣本不穩 (n=18/16, 沒 bootstrap CI)
3. Multiple testing (沒 correction)
4. 時間 clustering (18 個 case 集中在 1-2 個 drawdown?)
5. 沒 sub-period split
6. 反向因果不分
7. 閾值 sensitivity

## Round 0: cp 跟 fut 本身相關度

`pearson(cp, fut)` = **+0.263** (n=1537)

✓ cp 跟 fut 本身**只弱相關** (|r| = 0.26). DIVERGE 稀少不是因為高度共動.

## Round 1: Walk-forward z-score (移除 lookahead bias)

用 rolling 252-day window 算 z-score (= 1 年). 對 i 點, z 只用 [i-252, i-1] 資訊.

| Pattern | z-method | n | T+5 mean | T+5 95% CI | T+20 mean | T+20 95% CI |
|---|---|---:|---:|---|---:|---|
| DIVERGE cp 空 fut 多 | full | 18 | -4.15% | [-7.32, -1.07] | -0.70% | [-4.29, +2.57] |
| DIVERGE cp 空 fut 多 | walk-fwd 252d | 3 | — | — | — | — |
| DIVERGE cp 多 fut 空 | full | 16 | -0.55% | [-2.40, +0.81] | -3.06% | [-5.97, -0.27] |
| DIVERGE cp 多 fut 空 | walk-fwd 252d | 9 | +1.29% | [+0.55, +2.05] | +1.18% | [-0.34, +2.90] |
| BOTH_NEG (z<-1.5) | full | 4 | — | — | — | — |
| BOTH_NEG (z<-1.5) | walk-fwd 252d | 46 | -0.14% | [-1.29, +1.04] | +0.07% | [-1.49, +1.54] |
| BOTH_POS (z>+1.5) | full | 36 | +0.85% | [+0.23, +1.45] | +2.31% | [-0.19, +4.37] |
| BOTH_POS (z>+1.5) | walk-fwd 252d | 41 | +0.45% | [-0.25, +1.13] | -0.71% | [-2.64, +1.23] |

## Round 2: 時間 clustering — DIVERGE 分布在哪幾年?

用 walk-forward z-score 算的 DIVERGE 案例, 看年份分布.

**DIVERGE cp 空 fut 多** (n=3):

| 年份 | 次數 |
|---|---:|
| 2025 | 3 |

_(60 日內 ≥3 案例 集中度: 1 次)_

**DIVERGE cp 多 fut 空** (n=9):

| 年份 | 次數 |
|---|---:|
| 2021 | 1 |
| 2024 | 8 |

_(60 日內 ≥3 案例 集中度: 5 次)_

## Round 3: Bootstrap CI 細看 (n=2000 resample, 95% CI)

檢驗 v1 「cp 空 fut 多 → T+5 -4.15%」 finding 的 CI 寬度.

全段 z definition 下 n = 18

| Horizon | n | mean | 95% CI | baseline | CI 含 baseline? |
|---|---:|---:|---|---:|---|
| T+1 | 18 | -0.84% | [-1.73, +0.07] | +0.088% | **否 ⬇⬇** |
| T+5 | 18 | -4.15% | [-7.34, -1.09] | +0.437% | **否 ⬇⬇** |
| T+10 | 18 | -3.03% | [-6.75, +0.38] | +0.866% | **否 ⬇⬇** |
| T+20 | 18 | -0.70% | [-4.18, +2.81] | +1.713% | 是 (= 不顯著) |

## Round 4: Sub-period 分段 (排除單一 era 主導)

分界點: 2023-05-05 (TAIFEX 夜盤 endpoint cutoff). Era 1 = 2020-01-02~2023-05-04 (809 dates), Era 2 = 2023-05-05~2026-05-06 (728 dates)

| Era | DIVERGE n | T+5 mean | T+5 95% CI | T+20 mean |
|---|---:|---:|---|---:|
| Era 1 (2020~2023/5) | 18 | -4.15% | [-7.53, -1.17] | -0.70% |
| Era 2 (2023/5~2026/5) | 0 | — | — | — |

## Round 5: 閾值 sensitivity — z=±0.5/1.0/1.5/2.0

驗證 finding 對 z 閾值 robust. 用 walk-forward z. 看 cp_z<-T fut_z>+T 的 T+5 forward.

| z 閾值 | n | T+5 mean | T+5 95% CI |
|---|---:|---:|---|
| ±0.5 | 38 | +1.75% | [+0.91, +2.63] |
| ±1.0 | 3 | — | — |
| ±1.5 | 0 | — | — |
| ±2.0 | 0 | — | — |

## Round 6: 「fut 5d 持續極端負 → 反彈」 reanalysis

v1 findng: fut5d_z<-1.5 (n=51) → T+10 +2.31% ⬆ contrarian
用 walk-forward z 重測 + bootstrap CI + 看分布在哪幾年

用 walk-forward z (252d) 對 fut5d, 找 z<-1.5 點: n = 292

| Horizon | n | mean | 95% CI | baseline | 顯著? |
|---|---:|---:|---|---:|---|
| T+1 | 291 | +0.08% | [-0.08, +0.23] | +0.088% | 不顯著 |
| T+5 | 287 | +0.42% | [+0.09, +0.75] | +0.437% | 不顯著 |
| T+10 | 282 | +0.64% | [+0.18, +1.07] | +0.866% | 不顯著 |
| T+20 | 279 | +0.82% | [+0.27, +1.37] | +1.713% | **⬇⬇** |

年份分布: 2021: 92, 2023: 78, 2024: 101, 2025: 8, 2026: 13

## Round 7: Multiple testing correction + 最終 honest take

v1 跑 ~40 個 hypothesis test. Bonferroni corrected α = 0.05/40 = **0.0013** ≈ |t| > 3.2.
v1 的 |t|>2 (p≈0.046) **全部 fail Bonferroni**.

---

## 🔥 v1 findings 的 audit 結果（核彈級發現）

### v1 finding 1: 「cp 空 fut 多 → T+5 -4.15% 顯著下跌」 → **死於 Round 1+4**

| Audit | 結果 | Verdict |
|---|---|---|
| v1 (full z, n=18) | T+5 -4.15%, CI [-7.34, -1.09] ⬇⬇ | 看似顯著 |
| Round 1 walk-fwd z | **n=3 only** (太少不能算) | **死於 lookahead bias** |
| Round 4 era split | **18/18 全部在 Era 1 (2020-2023)** Era 2 = 0 | **regime-specific** |
| Round 5 閾值 sensitivity | z=±0.5 n=38 T+5 **+1.75%** (反向!) | **閾值不 robust** |

**真相**: v1 的 18 個 DIVERGE 案例**全部**集中在 2020-2023 covid+熊市 era. 用 walk-forward z 後 (= 移除 lookahead) 樣本崩到 3 個. 用更寬閾值 (±0.5) 反而出 **+1.75% 正向**. 整個 finding 是 **lookahead bias × regime-specific 雙重 artifact**.

### v1 finding 2: 「fut5d 持續極端負 → 反彈 +2.31%」 → **方向反了**

| Audit | 結果 | Verdict |
|---|---|---|
| v1 (full z, n=51) | T+10 +2.31% ⬆ | 看似 contrarian rebound |
| Round 6 walk-fwd z (n=292) | T+1/+5/+10 不顯著, **T+20 +0.82% (baseline +1.71%)** ⬇⬇ | **跟 v1 反過來** |
| 年份分布 | 2021:92 / 2023:78 / 2024:101 = 273/292 都在牛市 | regime-specific |

**真相**: 用 walk-forward z 重測, fut 持續極端負對應的是「牛市中法人加碼空頭、但大盤繼續漲、空頭跑輸 baseline 0.9%」. **不是 contrarian rebound, 是 underperform**. v1 的 +2.31% 是 lookahead bias 把所有極端值集中放大了.

### v1 finding 3: 「中性期報酬比 baseline 低」 → **survived 但不 actionable**

NEUTRAL n=237 的 T+5/+10/+20 都顯著低於 baseline. 但 NEUTRAL 是 majority of dates (15%~), 不是 tradable signal.

---

## 我的 honest take (這是 v2 真實結論, 不是 v1 那些 fragile claim)

### 1. v1 的所有「顯著 finding」全都被 audit 推翻
- DIVERGE 死於 lookahead + regime-specific
- 持續極端負 → 反彈 死於方向相反 (用 walk-fwd 算)
- v1 寫的時候**我自己審查不夠 rigorous**, 太 confident

### 2. cp 跟 fut 對加權**沒有**穩定預測力
- 同期 cp r=+0.30 (= concurrent 不是 forward)
- 全部 forward horizon r 接近 0
- 任何「條件式 forward」 finding 都 fragile

### 3. 用戶的 hypothesis 在 6 年資料**不成立**
- 「持續負部位 → 下跌壓力」: 6 年只有 4 個 BOTH_NEG (full z), walk-fwd 也只 46 個 → 樣本太少
- walk-fwd 下 BOTH_NEG T+5 -0.14%, CI [-1.29, +1.04] 包含 baseline → **不顯著**
- 反而 BOTH_POS walk-fwd T+5 +0.45% CI [-0.25, +1.13] 也包含 baseline → 都不顯著

### 4. 所有「significance」都需 Bonferroni 修正
- 40 tests × α=0.05 → expected 2 false positives
- v1 的 |t|>2 全部 fail Bonferroni (要 |t|>3.2 才嚴格顯著)
- v1 的 finding 數量恰好 ≈ false positive rate, 統計上 indistinguishable from noise

### 5. 為什麼 6 年資料不夠
- 1.5 個完整 market cycle (covid + bull + bear + bull)
- regime-specific finding 容易出現但不能 generalize
- Trading strategy 要 ≥30 個獨立事件 + out-of-sample test, 6 年達不到

### 6. 真正可用的 take-away
- **不能** 用 cp/fut z-score 單獨 build trading strategy
- **可能** 在極端事件 (next big bear) 看到信號, 但 6 年資料 detect 不到
- **應該** 加其他變數: VIX / 三大法人現貨買賣超 / VIX term structure / 殖利率曲線 / 散戶融資餘額變化
- **要做的下一步**: out-of-sample test (= 用 2026 後新進來的資料 forward test, 而不是 retrospective)

### 7. v1 vs v2 — 我學到的
**v1 的錯不是計算錯, 是「研究 framework 不夠嚴謹」**:
- 沒做 walk-forward → lookahead bias
- 沒做 sub-period → 沒 detect regime concentration
- 沒做 bootstrap CI → 把 small-N 樣本誤認為 robust
- 沒做 multiple testing correction → 把 noise 當 signal
- 太快 commit「白話結論」, 沒 self-audit

**這是 v2 的價值** — 用同樣資料、更 rigorous 方法, 把 v1 結論幾乎完全打掉. 這提醒我自己: 寫研究**永遠**要先 audit 再下結論, 不要 commit confidence 到 markdown 裡.

---

## v1 vs v2 對照表

| Finding | v1 結論 | v2 audit 後 |
|---|---|---|
| 兩者都極端負 → 跌 | 樣本太少 (n=4) | 不變 (walk-fwd n=46 也不顯著) |
| **cp 空 fut 多 → T+5 大跌** | **n=18, -4.15% ⬇⬇ 顯著** | **死: lookahead + regime** |
| cp 多 fut 空 → T+20 -3.06% | n=16 顯著 ⬇⬇ | walk-fwd n=9 變 +1.29% → 不確定 |
| **fut5d 持續負 → 反彈 +2.31%** | **顯著 ⬆ contrarian** | **方向反了**, walk-fwd T+20 跑輸 baseline 0.9% ⬇ |
| fut 主導看多 → +3.01% | n=162 顯著 ⬆ | 沒 re-audit (留待 v3) |

**核心教訓**: v1 寫得很 confident, 但 7 round audit 後**只有 2 個 finding 部分倖存** (BOTH 都不顯著、NEUTRAL 跑輸 baseline 但無 actionable value). 用戶的直覺「持續負 → 下跌壓力」 仍然**得不到統計支持**.
