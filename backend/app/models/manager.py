"""模型下载/缓存管理（§5, §6A, §17.5）。

设计要点（§17 验证结论）：
- 用 modelscope.snapshot_download 下载到 %LOCALAPPDATA%\\funasr-subtitle\\models。
- **torch-free**：本模块只 import modelscope，绝不安装 torch-stub
  （modelscope 的 logger 用 find_spec('torch')，发现 torch 就会 import 真 torch_utils）。
  torch-stub 只在 engine 里、且在 modelscope 完成初始化之后安装。
- SenseVoice 仓库含 893MB 的 model.pt（PyTorch 权重），onnx 下载时用 ignore_patterns 跳过，
  只取 *.onnx + 配置/词表；full 后端则下载 pt 权重。
- full 后端判定/下载走 ModelSpec.full_repo（及历史落盘路径），与 onnx 的 *.onnx 探测分开。
"""
from __future__ import annotations

import threading
from pathlib import Path
from typing import Callable, Optional

from ..config import models_dir
from .registry import REGISTRY, ModelSpec, get_model, resolve_full_repo

# onnx 下载时跳过的大文件（PyTorch 权重等）
_IGNORE_PATTERNS = ["*.pt", "*.pth", "*.bin", "*.safetensors", "*.onnx_data.bak"]
# full 后端认为「已下载」的权重后缀
_WEIGHT_GLOBS = ("*.pt", "*.bin", "*.pth", "*.safetensors")

# percent 0..100, downloaded_mb, total_mb
DownloadProgress = Callable[[float, float, float], None]


def _active_backend() -> str:
    """与 engine.backend() 同优先级，避免 manager↔engine 循环 import。"""
    import os

    env = os.environ.get("FUNASR_SUBTITLE_BACKEND")
    if env:
        return env.strip().lower()
    try:
        from .. import _build  # 构建期生成，未提交
        return str(getattr(_build, "BACKEND", "onnx")).strip().lower()
    except Exception:
        return "onnx"


class ModelManager:
    # 类级、跨实例共享的「按 model_id」下载锁：API 与 worker 各自持有不同的
    # ModelManager 实例却指向同一缓存目录，必须共享锁，避免并发下载互踩。
    _locks_guard = threading.Lock()
    _locks: "dict[str, threading.Lock]" = {}

    def __init__(self, root: Optional[Path] = None) -> None:
        self.root = root or models_dir()

    @classmethod
    def _lock_for(cls, model_id: str) -> threading.Lock:
        with cls._locks_guard:
            lk = cls._locks.get(model_id)
            if lk is None:
                lk = threading.Lock()
                cls._locks[model_id] = lk
            return lk

    # ---- 路径与状态 ----
    def local_dir(self, model_id: str) -> Path:
        """onnx 缓存约定：<root>/<repo>（repo 形如 owner/name）。"""
        spec = get_model(model_id)
        return self.root / spec.repo

    def full_local_dir(self, model_id: str) -> Path:
        """full 后端主下载路径：<root>/<full_repo>。"""
        spec = get_model(model_id)
        repo = resolve_full_repo(spec)
        if not repo:
            raise ValueError(f"model {model_id} has no full_repo")
        return self.root / repo

    def _full_repos(self, spec: ModelSpec) -> list[str]:
        repos: list[str] = []
        primary = resolve_full_repo(spec)
        if primary:
            repos.append(primary)
        fm = (spec.full_model or "").strip()
        if fm and "/" in fm and fm not in repos:
            repos.append(fm)
        for alt in spec.full_repo_alts:
            if alt and alt not in repos:
                repos.append(alt)
        return repos

    def _full_candidate_dirs(self, spec: ModelSpec) -> list[Path]:
        """MODELSCOPE_CACHE / snapshot_download 可能落在 root、root/models、root/hub。"""
        dirs: list[Path] = []
        seen: set[Path] = set()
        for repo in self._full_repos(spec):
            for base in (self.root, self.root / "models", self.root / "hub"):
                p = base / repo
                if p not in seen:
                    seen.add(p)
                    dirs.append(p)
        return dirs

    @staticmethod
    def _dir_has_weights(d: Path) -> bool:
        if not d.is_dir():
            return False
        return any(any(d.glob(g)) for g in _WEIGHT_GLOBS)

    def _onnx_base_dirs(self, spec: ModelSpec) -> list[Path]:
        """旧布局 <root>/<owner>/<name>；新 modelscope 可能是 <root>/models/<owner>--<name>。"""
        repo = spec.repo
        dashed = repo.replace("/", "--")
        dirs: list[Path] = []
        seen: set[Path] = set()
        for p in (
            self.root / repo,
            self.root / "models" / repo,
            self.root / "hub" / repo,
            self.root / dashed,
            self.root / "models" / dashed,
            self.root / "hub" / dashed,
        ):
            if p not in seen:
                seen.add(p)
                dirs.append(p)
        return dirs

    def _onnx_candidate_dirs(self, spec: ModelSpec) -> list[Path]:
        out: list[Path] = []
        seen: set[Path] = set()

        def add(p: Path) -> None:
            if p not in seen:
                seen.add(p)
                out.append(p)

        for base in self._onnx_base_dirs(spec):
            add(base)
            snap = base / "snapshots"
            if snap.is_dir():
                for rev in sorted(snap.iterdir()):
                    if rev.is_dir():
                        add(rev)
        return out

    def _onnx_dir_complete(self, spec: ModelSpec, d: Path) -> bool:
        if not (d.is_dir() and any(d.glob("*.onnx"))):
            return False
        for fname, _src in spec.aux_files:
            if not (d / fname).exists():
                return False
        for _src, dst in spec.local_copies:
            if not (d / dst).exists():
                return False
        return True

    def _onnx_ready_dir(self, spec: ModelSpec) -> Optional[Path]:
        return next((d for d in self._onnx_candidate_dirs(spec) if self._onnx_dir_complete(spec, d)), None)

    def _is_onnx_ready(self, spec: ModelSpec) -> bool:
        return self._onnx_ready_dir(spec) is not None

    def _is_full_ready(self, spec: ModelSpec) -> bool:
        if not (spec.full_model or spec.full_repo):
            return False
        return any(self._dir_has_weights(d) for d in self._full_candidate_dirs(spec))

    def is_downloaded(self, model_id: str) -> bool:
        spec = get_model(model_id)
        if _active_backend() == "full" and (spec.full_model or spec.full_repo):
            return self._is_full_ready(spec)
        return self._is_onnx_ready(spec)

    def resolve_dir(self, model_id: str) -> Path:
        """返回当前后端应使用的本地模型目录（已下载时优先已有路径）。"""
        spec = get_model(model_id)
        if _active_backend() == "full" and (spec.full_model or spec.full_repo):
            for d in self._full_candidate_dirs(spec):
                if self._dir_has_weights(d):
                    return d
            return self.full_local_dir(model_id)
        found = self._onnx_ready_dir(spec)
        return found if found else self.local_dir(model_id)

    def ensure_dir(self, model_id: str) -> Path:
        """返回本地模型目录；若缺失则同步下载（无进度回调）。"""
        if not self.is_downloaded(model_id):
            self.download(model_id)
        return self.resolve_dir(model_id)

    # ---- 下载 ----
    def download(self, model_id: str, progress: Optional[DownloadProgress] = None) -> Path:
        """同步下载。progress(percent, downloaded_mb, total_mb)。

        modelscope 自身的进度回调不稳定，这里用「后台线程下载 + 轮询目录大小」估算进度。
        full 后端下载 pt 仓库；onnx 后端下载 onnx 仓库（跳过 *.pt）。
        """
        spec = get_model(model_id)
        use_full = _active_backend() == "full" and bool(resolve_full_repo(spec))
        target = self.full_local_dir(model_id) if use_full else self.local_dir(model_id)

        if self.is_downloaded(model_id):
            if progress:
                progress(100.0, spec.size_mb, spec.size_mb)
            return self.resolve_dir(model_id)

        lock = self._lock_for(model_id)
        with lock:
            if self.is_downloaded(model_id):
                if progress:
                    progress(100.0, spec.size_mb, spec.size_mb)
                return self.resolve_dir(model_id)
            if use_full:
                return self._download_full_locked(spec, target, progress)
            return self._download_onnx_locked(spec, target, progress)

    def _download_onnx_locked(self, spec, target, progress):  # noqa: ANN001
        from modelscope.hub.snapshot_download import snapshot_download  # torch-free
        model_id = spec.id

        result: dict[str, object] = {}

        def _run() -> None:
            try:
                result["path"] = snapshot_download(
                    spec.repo,
                    cache_dir=str(self.root),
                    ignore_file_pattern=_IGNORE_PATTERNS,
                )
            except TypeError:
                try:
                    result["path"] = snapshot_download(
                        spec.repo,
                        cache_dir=str(self.root),
                        ignore_patterns=_IGNORE_PATTERNS,
                    )
                except Exception as e:  # noqa: BLE001
                    result["error"] = e
            except Exception as e:  # noqa: BLE001
                result["error"] = e

        self._wait_download(_run, target, spec, progress)

        if "error" in result:
            raise RuntimeError(f"download failed for {model_id}: {result['error']!r}")

        dest = Path(str(result["path"])) if result.get("path") else target
        if not self._onnx_dir_complete(spec, dest):
            dest = self._onnx_ready_dir(spec) or dest
        self._fetch_aux_files(spec, dest)
        self._make_local_copies(spec, dest)

        if progress:
            got = _dir_size(dest)
            progress(100.0, round(got / 1024 / 1024, 1), spec.size_mb)
        return dest if self._onnx_dir_complete(spec, dest) else self.resolve_dir(model_id)

    def _download_full_locked(self, spec, target, progress):  # noqa: ANN001
        from modelscope.hub.snapshot_download import snapshot_download  # torch-free
        model_id = spec.id
        repo = resolve_full_repo(spec)
        if not repo:
            raise RuntimeError(f"no full_repo for {model_id}")

        result: dict[str, object] = {}

        def _run() -> None:
            try:
                # full：需要 pt 权重，不 ignore *.pt
                result["path"] = snapshot_download(repo, cache_dir=str(self.root))
            except Exception as e:  # noqa: BLE001
                result["error"] = e

        self._wait_download(_run, target, spec, progress)

        if "error" in result:
            raise RuntimeError(f"download failed for {model_id}: {result['error']!r}")

        if progress:
            got = _dir_size(target)
            progress(100.0, round(got / 1024 / 1024, 1), spec.size_mb)
        return self.resolve_dir(model_id)

    def _wait_download(self, run_fn, target, spec, progress):  # noqa: ANN001
        t = threading.Thread(target=run_fn, daemon=True)
        t.start()
        total_bytes = spec.size_mb * 1024 * 1024
        if progress:
            progress(0.0, 0.0, spec.size_mb)
        while t.is_alive():
            t.join(timeout=0.5)
            if progress:
                got = _dir_size(target)
                pct = min(99.0, got / total_bytes * 100.0) if total_bytes else 0.0
                progress(round(pct, 1), round(got / 1024 / 1024, 1), spec.size_mb)

    def _fetch_aux_files(self, spec: ModelSpec, target: Path) -> None:
        if not spec.aux_files:
            return
        import shutil

        from modelscope.hub.snapshot_download import snapshot_download  # torch-free

        for fname, src_repo in spec.aux_files:
            if (target / fname).exists():
                continue
            try:
                src_dir = Path(snapshot_download(
                    src_repo, cache_dir=str(self.root), allow_file_pattern=[fname]))
            except TypeError:
                src_dir = Path(snapshot_download(
                    src_repo, cache_dir=str(self.root), allow_patterns=[fname]))
            src = src_dir / fname
            if src.exists():
                shutil.copy2(src, target / fname)
            else:
                raise RuntimeError(
                    f"aux file {fname} not found in {src_repo} for {spec.id}")

    def _make_local_copies(self, spec: ModelSpec, target: Path) -> None:
        if not spec.local_copies:
            return
        import shutil

        for src_name, dst_name in spec.local_copies:
            src, dst = target / src_name, target / dst_name
            if dst.exists():
                continue
            if src.exists():
                shutil.copy2(src, dst)
            else:
                raise RuntimeError(
                    f"local copy source {src_name} missing in {spec.id}")

    # ---- 目录列举（给 /api/models） ----
    def status(self, model_id: str) -> bool:
        return self.is_downloaded(model_id)

    def all_specs(self) -> list[ModelSpec]:
        return list(REGISTRY.values())


def _dir_size(path: Path) -> float:
    if not path.exists():
        return 0.0
    total = 0
    for p in path.rglob("*"):
        if p.is_file():
            try:
                total += p.stat().st_size
            except OSError:
                pass
    return float(total)
