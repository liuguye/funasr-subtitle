@echo off
setlocal
cd /d "%~dp0"

if not exist "backend\.venv\Scripts\python.exe" (
  echo [error] backend\.venv not found. Create the venv first.
  pause
  exit /b 1
)

pushd backend
start "funasr-subtitle backend" cmd /k ".venv\Scripts\python -m uvicorn app.main:app --reload --port 8765"
popd

pushd frontend
if not exist "node_modules\" call npm ci
start "funasr-subtitle frontend" cmd /k "npm run dev"
popd
endlocal
