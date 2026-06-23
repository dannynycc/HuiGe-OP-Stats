# 自動更新排程（為什麼不靠 GitHub 內建 cron）

## TL;DR

本 repo 的「每天自動更新 3 次」**主力靠外部排程器**（cron-job.org）每天定時呼叫
GitHub API 的 `workflow_dispatch` 來觸發 `update-data` workflow。
`update.yml` 裡保留的 3 班 `schedule` cron 只是**備援**。

## 為什麼不用 `update.yml` 裡的 GitHub 內建 cron？

2026-06-23 實測發現：**本 repo 的 GitHub 內建排程（`schedule` 事件）完全不觸發。**

- push / `workflow_dispatch`（手動）/ `pages-build-deployment` 都正常運作 → runner、
  額度、Actions infra 都沒問題。
- 但 `gh run list --workflow update.yml --event schedule` 從頭到尾 **0 筆**。
- 兩次測試班（一次 11 分提前量、一次 34 分提前量且避開整點）排程時間到了都沒跑。
- 原因未定論：可能是「新加的排程 GitHub 排程器尚未納入」，也可能是 GitHub 排程器
  對此 repo 不可靠。無論哪種，**都不能拿來當每日更新的依靠**。

> 註：GitHub 官方亦明載 `schedule` 在高負載（尤其每小時整點 `:00`）會被延遲甚至
> 丟棄，且新建排程的第一班最不準。即使之後活過來，也不適合當主力。

## 外部排程器設定（cron-job.org）

### 1. 建 fine-grained PAT（權限最小化）

GitHub → Settings → Developer settings → Personal access tokens → **Fine-grained tokens**
→ Generate new token

- Resource owner：`dannynycc`
- Repository access：**Only select repositories** → `HuiGe-OP-Stats`
- Permissions → Repository permissions → **Actions：Read and write**（其餘不動）
- Expiration：設長一點；到期前 GitHub 會 email 提醒，到期後需重新產生並更新到 cron-job.org

### 2. cron-job.org 建 job

| 欄位 | 值 |
|---|---|
| URL | `https://api.github.com/repos/dannynycc/HuiGe-OP-Stats/actions/workflows/update.yml/dispatches` |
| Method | `POST` |
| Schedule | 時區 `Asia/Taipei`，時間 `15:00` / `21:00` / `07:00` |
| Header `Accept` | `application/vnd.github+json` |
| Header `Authorization` | `Bearer <PAT>` |
| Header `X-GitHub-Api-Version` | `2022-11-28` |
| Header `Content-Type` | `application/json` |
| Body | `{"ref":"main"}` |

### 3. 驗證

cron-job.org 該 job 按 **Run now / Test run** → 回 GitHub repo → Actions → 應出現一筆新的
`update-data`（event = `workflow_dispatch`）。成功回應為 **HTTP 204 No Content**。

本機快測（token 用環境變數，勿寫進檔案 / 對話）：

```bash
curl -X POST \
  -H "Authorization: Bearer $GH_PAT" \
  -H "Accept: application/vnd.github+json" \
  -H "X-GitHub-Api-Version: 2022-11-28" \
  https://api.github.com/repos/dannynycc/HuiGe-OP-Stats/actions/workflows/update.yml/dispatches \
  -d '{"ref":"main"}'
```

## 維護備註

- PAT 到期 → 自動更新會悄悄停掉（cron-job.org 會收到 401）。到期前換新 token。
- 想完全移除備援 cron，把 `update.yml` 的 `schedule:` 區塊整段刪掉即可，不影響外部觸發。
