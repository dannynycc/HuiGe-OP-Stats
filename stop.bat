@echo off
echo Stopping uvicorn on port 8765 ...
for /f "tokens=5" %%P in ('netstat -ano ^| findstr "127.0.0.1:8765" ^| findstr LISTENING') do (
    taskkill /F /PID %%P 2>nul
)
echo Done.
