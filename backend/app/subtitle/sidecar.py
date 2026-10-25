"""把字幕写到源媒体旁边。

`video.mp4` + 格式 srt → 同目录 `video.srt`。只碰字幕文件，不改、不删源文件。
"""
from __future__ import annotations

from pathlib import Path

from ..schemas import Segment
from .formatters import EXPORT_FORMATS, export_segments


def write_beside(
    source: Path,
    segments: list[Segment],
    formats: list[str],
) -> tuple[list[str], list[str]]:
    """写入 `source` 同目录的字幕。返回 (写成的绝对路径, 给人看的错误)。"""
    written: list[str] = []
    errors: list[str] = []
    if not source.is_file():
        return written, ["找不到源文件，字幕没写到磁盘。"]

    parent = source.parent
    origin = source.resolve()
    seen: set[str] = set()
    for fmt in formats:
        key = fmt.lower().lstrip(".")
        if key in seen:
            continue
        seen.add(key)
        spec = EXPORT_FORMATS.get(key)
        if spec is None:
            errors.append(f"不支持 .{key}")
            continue
        _mime, ext = spec
        stem = source.stem.strip() or "subtitle"
        dest = parent / f"{stem}.{ext}"
        try:
            if dest.resolve() == origin:
                errors.append(f"{dest.name} 会盖住源文件，已跳过")
                continue
            body = export_segments(segments, key)
            dest.write_bytes(body.encode("utf-8"))
        except OSError as exc:
            errors.append(f"{dest.name} 写不进去（{exc.strerror or exc}）")
            continue
        except ValueError as exc:
            errors.append(str(exc))
            continue
        written.append(str(dest))
    return written, errors


def describe_outputs(
    source: Path | None,
    segments: list[Segment],
    formats: list[str] | None,
) -> dict:
    """给完成事件 / 查询接口的说明。`formats is None` 表示调用方没指定，有源路径时默认 srt。"""
    if source is None:
        return {
            "source_path": None,
            "written_files": [],
            "write_error": None,
            "output_note": "没有本机路径，字幕只留在页面里，可以下载。",
        }

    chosen = ["srt"] if formats is None else list(formats)
    if not chosen:
        return {
            "source_path": str(source),
            "written_files": [],
            "write_error": None,
            "output_note": "没有选择要写入的格式，未写到磁盘。",
        }

    written, errors = write_beside(source, segments, chosen)
    if errors and written:
        note = f"写了 {len(written)} 个文件，还有没写进去的。"
    elif errors:
        note = "字幕没能写到源文件旁边。"
    else:
        note = "已写到源文件旁边。"
    return {
        "source_path": str(source),
        "written_files": written,
        "write_error": "；".join(errors) if errors else None,
        "output_note": note,
    }
