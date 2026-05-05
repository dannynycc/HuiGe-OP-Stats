@echo off
cd /d %~dp0
echo Starting 法人OP server on http://localhost:8765 ...
start "OP-DAY-NIGHT" /min powershell -WindowStyle Hidden -Command "python -m uvicorn app.main:app --host 127.0.0.1 --port 8765 *> logs\server.log"
timeout /t 2 /nobreak >nul
echo Open  http://localhost:8765
