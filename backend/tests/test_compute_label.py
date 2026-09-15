"""compute_label / backend 与环境变量一致。"""
from __future__ import annotations

import sys
import types

import pytest


@pytest.fixture(autouse=True)
def _clear_backend_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("FUNASR_SUBTITLE_BACKEND", raising=False)
    monkeypatch.delenv("FUNASR_SUBTITLE_FORCE_CPU", raising=False)


def test_compute_label_onnx(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("FUNASR_SUBTITLE_BACKEND", "onnx")
    from app.engine import compute_label
    assert compute_label() == "CPU · onnx"


def test_compute_label_full_no_torch(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("FUNASR_SUBTITLE_BACKEND", "full")
    # 若环境里已有 torch，此测试仍应返回 CPU · full 或 GPU · CUDA；
    # 用 stub 屏蔽 cuda。
    fake = types.ModuleType("torch")
    fake.cuda = types.SimpleNamespace(is_available=lambda: False)
    monkeypatch.setitem(sys.modules, "torch", fake)
    from app.engine import compute_label
    assert compute_label() == "CPU · full"


def test_compute_label_full_cuda(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("FUNASR_SUBTITLE_BACKEND", "full")
    fake = types.ModuleType("torch")
    fake.cuda = types.SimpleNamespace(is_available=lambda: True)
    monkeypatch.setitem(sys.modules, "torch", fake)
    from app.engine import compute_label
    assert compute_label() == "GPU · CUDA"


def test_compute_label_force_cpu(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("FUNASR_SUBTITLE_BACKEND", "full")
    monkeypatch.setenv("FUNASR_SUBTITLE_FORCE_CPU", "1")
    fake = types.ModuleType("torch")
    fake.cuda = types.SimpleNamespace(is_available=lambda: True)
    monkeypatch.setitem(sys.modules, "torch", fake)
    from app.engine import compute_label
    assert compute_label() == "CPU · full"
