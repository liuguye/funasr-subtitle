"""ModelManager 下载状态：onnx 认 *.onnx；full 认 pt 权重及 MODELSCOPE_CACHE 落盘路径。"""
from __future__ import annotations

from pathlib import Path

import pytest

from app.models.manager import ModelManager
from app.models.registry import (
    PARAFORMER_ZH,
    PARAFORMER_ZH_HOTWORD,
    SENSEVOICE,
)


@pytest.fixture()
def mgr(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> ModelManager:
    monkeypatch.setenv("FUNASR_SUBTITLE_BACKEND", "onnx")
    return ModelManager(tmp_path)


def _touch(path: Path, name: str = "model.pt") -> None:
    path.mkdir(parents=True, exist_ok=True)
    (path / name).write_bytes(b"x")


def test_onnx_ready_requires_onnx_and_aux(mgr: ModelManager) -> None:
    assert not mgr.is_downloaded(SENSEVOICE.id)
    d = mgr.local_dir(SENSEVOICE.id)
    d.mkdir(parents=True)
    (d / "model_quant.onnx").write_bytes(b"o")
    # SenseVoice 还缺 bpe aux
    assert not mgr.is_downloaded(SENSEVOICE.id)
    (d / "chn_jpn_yue_eng_ko_spectok.bpe.model").write_bytes(b"b")
    assert mgr.is_downloaded(SENSEVOICE.id)


def test_full_backend_detects_pt_under_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("FUNASR_SUBTITLE_BACKEND", "full")
    mgr = ModelManager(tmp_path)
    assert not mgr.is_downloaded(PARAFORMER_ZH.id)
    _touch(tmp_path / PARAFORMER_ZH.full_repo)
    assert mgr.is_downloaded(PARAFORMER_ZH.id)
    assert mgr.resolve_dir(PARAFORMER_ZH.id) == tmp_path / PARAFORMER_ZH.full_repo


def test_full_backend_detects_modelscope_nested_cache(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AutoModel + MODELSCOPE_CACHE=models_dir 时常落在 root/models/<repo>。"""
    monkeypatch.setenv("FUNASR_SUBTITLE_BACKEND", "full")
    mgr = ModelManager(tmp_path)
    nested = tmp_path / "models" / PARAFORMER_ZH.full_repo
    _touch(nested)
    assert mgr.is_downloaded(PARAFORMER_ZH.id)
    assert mgr.resolve_dir(PARAFORMER_ZH.id) == nested


def test_full_backend_detects_seaco_underscore_alt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("FUNASR_SUBTITLE_BACKEND", "full")
    mgr = ModelManager(tmp_path)
    alt = "iic/speech_seaco_paraformer_large_asr_nat-zh-cn-16k-common-vocab8404-pytorch"
    _touch(tmp_path / "models" / alt)
    assert mgr.is_downloaded(PARAFORMER_ZH_HOTWORD.id)
    # 普通 Paraformer-zh 也把该 alt 列为探测路径（新版别名可能落到 SeACo）
    assert mgr.is_downloaded(PARAFORMER_ZH.id)


def test_onnx_backend_ignores_pt_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("FUNASR_SUBTITLE_BACKEND", "onnx")
    mgr = ModelManager(tmp_path)
    _touch(tmp_path / PARAFORMER_ZH.full_repo)
    assert not mgr.is_downloaded(PARAFORMER_ZH.id)
