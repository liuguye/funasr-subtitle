"""推理引擎层（§10）。

把推理封装在 ASREngine 抽象后面，让模型 / execution provider 可替换。
§17 验证结论见本目录 README.md。
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from ..config import NUM_THREADS, models_dir
from ..models import DEFAULT_MODEL_ID
from .base import ASREngine, EngineOptions, ProgressCallback, Stage


def backend() -> str:
    """推理后端：'onnx'（默认，funasr-onnx 纯 CPU）| 'full'（完整 funasr + torch/CUDA）。

    优先级：环境变量 FUNASR_SUBTITLE_BACKEND（便于同机切换测试）> 构建期烘焙的
    app/_build.py（由 build.ps1 -Variant 写入）> 默认 onnx。
    """
    env = os.environ.get("FUNASR_SUBTITLE_BACKEND")
    if env:
        return env.strip().lower()
    try:
        from .. import _build  # 构建期生成，未提交
        return str(getattr(_build, "BACKEND", "onnx")).strip().lower()
    except Exception:
        return "onnx"


def compute_label() -> str:
    """供 UI 显示的算力标签（与真实推理设备一致）。

    - full + CUDA 可用且未强制 CPU → ``GPU · CUDA``
    - full 但无 CUDA / 强制 CPU → ``CPU · full``
    - onnx 后端 → ``CPU · onnx``（不看显卡；onnx 路径默认不上 CUDA）
    """
    if backend() != "full":
        return "CPU · onnx"
    force_cpu = os.environ.get("FUNASR_SUBTITLE_FORCE_CPU") == "1"
    try:
        import torch
        if (not force_cpu) and torch.cuda.is_available():
            return "GPU · CUDA"
    except Exception:
        pass
    return "CPU · full"


def build_engine(
    model_id: str = "",
    *,
    models_root: Optional[str] = None,
    use_gpu: bool = False,
    num_threads: int = 0,
    diarization: bool = False,
) -> "ASREngine":
    """按后端构造引擎实例（onnx -> FunasrEngine；full -> FunasrFullEngine）。

    num_threads 未显式指定（<=0）时用 config.NUM_THREADS（env FUNASR_SUBTITLE_NUM_THREADS）。
    """
    opts = EngineOptions(
        model_id=model_id or DEFAULT_MODEL_ID,
        models_root=models_root or str(models_dir()),
        use_gpu=use_gpu,
        num_threads=num_threads if num_threads and num_threads > 0 else NUM_THREADS,
        diarization=diarization,
    )
    if backend() == "full":
        from .funasr_full_engine import FunasrFullEngine
        return FunasrFullEngine(opts)
    from .funasr_engine import FunasrEngine
    return FunasrEngine(opts)


__all__ = [
    "ASREngine",
    "EngineOptions",
    "ProgressCallback",
    "Stage",
    "backend",
    "compute_label",
    "build_engine",
]
