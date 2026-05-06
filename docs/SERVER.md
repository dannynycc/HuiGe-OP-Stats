# Server 啟動 / 停止 完整教學

> 路徑: `D:\ClaudeCode\法人OP日夜盤數據`
> Port: **8765** (固定)
> 入口: `app/main.py` 的 FastAPI app

---

## 一鍵 啟動 / 停止 (推薦)

repo 根目錄已備好兩個 `.bat`，**雙擊就動**：

| 動作 | 檔案 | 作用 |
|---|---|---|
| 啟動 | `start.bat` | 背景啟動 uvicorn (Hidden window)，log 寫到 `logs/server.log` |
| 停止 | `stop.bat` | 找出佔用 8765 的 PID 全部 `taskkill /F` |

啟動後瀏覽器打開：
- 主表 (柴柴 6 列彙整): <http://localhost:8765/>
- 綜合整理: <http://localhost:8765/comprehensive>
- 走勢圖: <http://localhost:8765/chart>

---

## start.bat 內容

```bat
@echo off
cd /d %~dp0
echo Starting 法人OP server on http://localhost:8765 ...
start "OP-DAY-NIGHT" /min powershell -WindowStyle Hidden -Command ^
  "python -m uvicorn app.main:app --host 127.0.0.1 --port 8765 *> logs\server.log"
timeout /t 2 /nobreak >nul
echo Open  http://localhost:8765
```

關鍵:
- `start /min` → 啟動新進程, minimize
- `-WindowStyle Hidden` → 視窗完全隱藏 (背景跑)
- `*> logs\server.log` → stdout + stderr 都導到 log 檔
- 沒有 `--reload` → production 模式 (改 code 不會自動 restart, 要手動)

## stop.bat 內容

```bat
@echo off
echo Stopping uvicorn on port 8765 ...
for /f "tokens=5" %%P in ('netstat -ano ^| findstr "127.0.0.1:8765" ^| findstr LISTENING') do (
    taskkill /F /PID %%P 2>nul
)
echo Done.
```

邏輯:
1. `netstat -ano` 列全部連線 + PID
2. `findstr "127.0.0.1:8765"` 篩本地 8765 port
3. `findstr LISTENING` 只要 listening (= server) 不要 client connection
4. 第 5 token = PID → `taskkill /F` 強制殺掉

---

## 手動啟動 (debug 用 / 看即時 log)

不想跑背景, 要直接看 server log + 改 code 即時 reload, 在 PowerShell 執行：

```powershell
cd D:\ClaudeCode\法人OP日夜盤數據
python -m uvicorn app.main:app --host 127.0.0.1 --port 8765 --reload
```

- `--reload`: 改 `app/*.py` 自動重啟 server (dev mode)
- 視窗關掉 = server 也掛 (Ctrl+C 也行)
- log 直接顯示在 console

## 手動停止

如果 `stop.bat` 抓不到 (e.g. 你開了多個 instance)：

```powershell
# 看看誰佔著 8765
netstat -ano | findstr 8765

# 殺特定 PID
Stop-Process -Id <PID> -Force

# 或殺全部 python (粗暴, 會殺到別的 python 程式, 慎用)
Get-Process python | Stop-Process -Force
```

---

## 完整重啟流程 (改完 code 之後)

```bat
stop.bat
start.bat
```

或一行:
```bat
stop.bat && start.bat
```

> 用 `start.bat`/`stop.bat` 是 [user feedback memory](
> ../../../../Users/Home/.claude/projects/C--Users-Home/memory/feedback_restart_flow.md)
> 的硬規則 — 不要手動 PowerShell 殺 python 進程, 容易累積 stale 進程 + 開了一堆瀏覽器分頁.

---

## 啟動成功確認

```powershell
# 1. 看 port 有沒有 listening
netstat -ano | findstr 8765
# 應該看到一行 LISTENING

# 2. 打 health endpoint (= 主頁)
curl http://127.0.0.1:8765/api/comprehensive
# 應該回 JSON

# 3. 看 log 沒有 error
Get-Content logs\server.log -Tail 20
```

如果 `start.bat` 跑完但 port 沒 listening:
- 看 `logs\server.log` 找錯誤訊息
- 常見問題:
  - port 8765 被別人佔 → `stop.bat` 再 `start.bat`
  - python module 缺 → `pip install -r requirements.txt`
  - DB lock 錯 → 別開兩個 instance, SQLite 不能 concurrent write

---

## 環境需求

- **Python 3.10+** (測過 3.13.5)
- 套件 (`requirements.txt`):
  - fastapi
  - uvicorn[standard]
  - requests
  - beautifulsoup4
  - lxml
  - openpyxl

第一次安裝:
```powershell
cd D:\ClaudeCode\法人OP日夜盤數據
pip install -r requirements.txt
```

---

## 目錄結構 (server-related)

```
D:\ClaudeCode\法人OP日夜盤數據\
├── start.bat         # 啟動 (背景)
├── stop.bat          # 停止
├── app/
│   ├── main.py       # FastAPI app entry (uvicorn 載入這個)
│   ├── refresh.py    # /api/refresh 邏輯
│   ├── db.py         # SQLite schema
│   ├── scrapers/     # 12 endpoint 爬蟲
│   └── static/       # HTML/JS/CSS (index.html / comprehensive.html / chart.html)
├── data/
│   └── data.db       # SQLite (gitignore)
├── logs/
│   └── server.log    # stdout/stderr 全寫這裡 (gitignore)
└── docs/
    └── SERVER.md     # 本檔
```

---

## TL;DR

| 我要... | 做這個 |
|---|---|
| 開站 | 雙擊 `start.bat` |
| 關站 | 雙擊 `stop.bat` |
| 改 code 之後重啟 | `stop.bat` 然後 `start.bat` |
| 看 server log | `Get-Content logs\server.log -Tail 30` |
| Debug (要看即時 log) | PowerShell 跑 `python -m uvicorn app.main:app --port 8765 --reload` |
| 確認有起來 | 瀏覽器開 <http://localhost:8765/> |
