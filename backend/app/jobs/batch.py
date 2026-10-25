"""在现有队列上补两件事：本机路径入队，以及完成时把字幕写到源文件旁边。

不改 Job 的字段定义。写盘结果放在管理器自己的 `output_meta` 里，
并通过队列的 `_before_done` 钩子并进 WebSocket 的 done 载荷。
"""
from __future__ import annotations

import contextvars
from pathlib import Path

from ..schemas import Job, JobOptions
from ..subtitle.sidecar import describe_outputs
from .queue import JobManager

_CREATE_EXTRA: contextvars.ContextVar[dict | None] = contextvars.ContextVar(
    "funasr_batch_create_extra", default=None,
)


class BatchJobManager(JobManager):
    def __init__(self) -> None:
        super().__init__()
        self._owned: dict[str, bool] = {}
        self._sources: dict[str, Path] = {}
        # None = 没指定（有源路径时默认 srt）；[] = 明确不写盘
        self._formats: dict[str, list[str] | None] = {}
        self.output_meta: dict[str, dict] = {}

    def create(  # type: ignore[override]
        self,
        filename: str,
        input_path: Path,
        options: JobOptions,
        *,
        source_path: Path | None = None,
        owned_input: bool = True,
        export_formats: list[str] | None = None,
    ) -> Job:
        # 必须在 super().create 入队之前写上，worker 可能马上就把任务取走。
        token = _CREATE_EXTRA.set({
            "source_path": source_path,
            "owned_input": owned_input,
            "export_formats": export_formats,
        })
        try:
            return super().create(filename, input_path, options)
        finally:
            _CREATE_EXTRA.reset(token)

    def _note_created(self, job: Job, input_path: Path) -> None:
        extra = _CREATE_EXTRA.get()
        if not extra:
            self._owned[job.id] = True
            return
        self._owned[job.id] = bool(extra.get("owned_input", True))
        src = extra.get("source_path")
        if src:
            self._sources[job.id] = Path(src)
        self._formats[job.id] = extra.get("export_formats")

    def _should_delete_input(self, job_id: str, path: Path) -> bool:
        owned = self._owned.pop(job_id, True)
        self._sources.pop(job_id, None)
        self._formats.pop(job_id, None)
        return owned

    def _before_done(self, job: Job) -> dict | None:
        source = self._sources.get(job.id)
        # 键不存在 = 旧的 create，没指定格式（有源路径时 describe_outputs 默认 srt）。
        # 键存在且值为 None，同样表示「没指定」；空列表表示用户明确不写盘。
        formats = self._formats[job.id] if job.id in self._formats else None
        info = describe_outputs(source, list(job.segments), formats)
        self.output_meta[job.id] = info
        for stale in [key for key in self.output_meta if key not in self.jobs]:
            self.output_meta.pop(stale, None)
        return info
