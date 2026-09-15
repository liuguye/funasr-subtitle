@echo off
setlocal
cd /d "%~dp0"

REM Prefer full/CUDA venv when present; otherwise onnx/CPU.
set "BACKEND=onnx"
set "VENV_PY=.venv\Scripts\python.exe"
if exist "backend\.venv-full\Scripts\python.exe" (
  set "BACKEND=full"
  set "VENV_PY=.venv-full\Scripts\python.exe"
  echo [dev] using full/CUDA backend: backend\.venv-full
) else (
  if not exist "backend\.venv\Scripts\python.exe" (
    echo [error] backend\.venv not found. Create the venv first.
    echo         For GPU: create backend\.venv-full + install torch CUDA, see backend\requirements-full.txt
    pause
    exit /b 1
  )
  echo [dev] using onnx/CPU backend: backend\.venv
  echo       To enable GPU: create backend\.venv-full and re-run this script.
)

pushd backend
start "funasr-subtitle backend" cmd /k "set FUNASR_SUBTITLE_BACKEND=%BACKEND%&& %VENV_PY% -m uvicorn app.main:app --reload --port 8765"
popd

pushd frontend
if not exist "node_modules\" call npm ci
start "funasr-subtitle frontend" cmd /k "npm run dev"
popd
endlocal
