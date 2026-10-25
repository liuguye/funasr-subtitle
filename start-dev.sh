#!/usr/bin/env bash
# 开发启动：后台 + 前端。用法：
#   ./start-dev.sh              # 后台 8765，页面 5173
#   ./start-dev.sh 9000         # 后台改到 9000（Vite 代理跟着走）
#   VITE_PORT=5174 ./start-dev.sh 9000
# Ctrl+C 结束两边。指定端口被占用时直接失败，不会顺延。
set -euo pipefail
cd "$(dirname "$0")"

PORT="${1:-${FUNASR_SUBTITLE_PORT:-8765}}"
UI_PORT="${VITE_PORT:-5173}"

if [[ -x backend/.venv-full/bin/python ]]; then
  PY="backend/.venv-full/bin/python"
  export FUNASR_SUBTITLE_BACKEND=full
  echo "[dev] using full/CUDA backend: backend/.venv-full"
elif [[ -x backend/.venv/bin/python ]]; then
  PY="backend/.venv/bin/python"
  export FUNASR_SUBTITLE_BACKEND="${FUNASR_SUBTITLE_BACKEND:-onnx}"
  echo "[dev] using backend venv: backend/.venv"
elif command -v python3 >/dev/null 2>&1; then
  PY="python3"
  export FUNASR_SUBTITLE_BACKEND="${FUNASR_SUBTITLE_BACKEND:-onnx}"
  echo "[dev] using python3 on PATH（没有 backend/.venv）"
else
  echo "[error] 找不到 Python。先建 backend/.venv" >&2
  exit 1
fi

if [[ ! -d frontend/node_modules ]]; then
  (cd frontend && npm ci)
fi

export FUNASR_SUBTITLE_PORT="$PORT"
export VITE_BACKEND_PORT="$PORT"
export VITE_PORT="$UI_PORT"

echo "[dev] backend :$PORT   frontend :$UI_PORT"
set -m
cleanup() {
  echo
  echo "[dev] stopping..."
  jobs -p | xargs -r kill 2>/dev/null || true
}
trap cleanup EXIT INT TERM
(cd backend && exec "$PY" -m uvicorn app.main:app --reload --port "$PORT") &
(cd frontend && exec npm run dev) &
wait || true
