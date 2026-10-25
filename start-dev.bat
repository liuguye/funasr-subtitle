@echo off
setlocal
cd /d "%~dp0"

REM 端口：start-dev.bat 9000  或  set FUNASR_SUBTITLE_PORT=9000
REM 页面端口另设 VITE_PORT（默认 5180，不用 5173，避免和本机其他 Vite 服务冲突）。
REM 后台被占用时 uvicorn 会直接失败，不会偷偷换端口。
set "PORT=8765"
if not "%~1"=="" set "PORT=%~1"
if "%~1"=="" if not "%FUNASR_SUBTITLE_PORT%"=="" set "PORT=%FUNASR_SUBTITLE_PORT%"
if "%VITE_PORT%"=="" set "VITE_PORT=5180"

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

if not exist "frontend\node_modules\" (
  pushd frontend
  call npm ci
  if errorlevel 1 (
    popd
    echo [error] npm ci failed
    pause
    exit /b 1
  )
  popd
)

echo [dev] starting backend :%PORT% and frontend :%VITE_PORT% in this window. Ctrl+C to stop both.
echo.

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$root = Get-Location;" ^
  "$backendDir = Join-Path $root 'backend';" ^
  "$frontendDir = Join-Path $root 'frontend';" ^
  "$py = Join-Path $backendDir '%VENV_PY%';" ^
  "$env:FUNASR_SUBTITLE_BACKEND = '%BACKEND%';" ^
  "$env:FUNASR_SUBTITLE_PORT = '%PORT%';" ^
  "$env:VITE_BACKEND_PORT = '%PORT%';" ^
  "$env:VITE_PORT = '%VITE_PORT%';" ^
  "Write-Host '[backend] uvicorn :%PORT%';" ^
  "$be = Start-Process -FilePath $py -ArgumentList '-m','uvicorn','app.main:app','--reload','--port','%PORT%' -WorkingDirectory $backendDir -NoNewWindow -PassThru;" ^
  "Write-Host '[frontend] npm run dev :%VITE_PORT%';" ^
  "$fe = Start-Process -FilePath 'npm.cmd' -ArgumentList 'run','dev' -WorkingDirectory $frontendDir -NoNewWindow -PassThru;" ^
  "$pids = @($be.Id, $fe.Id);" ^
  "function Stop-Dev {" ^
  "  foreach ($id in $pids) {" ^
  "    if (-not $id) { continue }" ^
  "    Start-Process -FilePath 'taskkill.exe' -ArgumentList '/PID',$id,'/T','/F' -Wait -WindowStyle Hidden -ErrorAction SilentlyContinue | Out-Null" ^
  "  }" ^
  "}" ^
  "try {" ^
  "  while ($true) {" ^
  "    Start-Sleep -Milliseconds 500;" ^
  "    $be.Refresh(); $fe.Refresh();" ^
  "    if ($be.HasExited -or $fe.HasExited) { break }" ^
  "  }" ^
  "} finally {" ^
  "  Write-Host ''; Write-Host '[dev] stopping...';" ^
  "  Stop-Dev" ^
  "}"

endlocal
