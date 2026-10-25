"""本机路径解析：批量队列要知道源文件的真实位置，才能把字幕写到旁边。

浏览器里的 File 通常没有绝对路径，所以由本机服务核对用户填的路径。
文件夹只展开一层，避免一次扫进整个磁盘。
"""
from __future__ import annotations

from pathlib import Path

# 和前端拖放区接受的容器对齐。点名某个文件时不看后缀（交给 ffmpeg 判断）。
MEDIA_SUFFIXES = {
    ".mp3", ".m4a", ".aac", ".wav", ".flac", ".ogg", ".oga", ".opus", ".wma",
    ".aiff", ".aif", ".alac", ".ape", ".wv", ".amr", ".ac3", ".mka", ".caf", ".dts",
    ".mp4", ".m4v", ".mkv", ".mov", ".avi", ".wmv", ".flv", ".webm", ".ts", ".m2ts",
    ".mts", ".vob", ".mpg", ".mpeg", ".3gp", ".3g2", ".ogv", ".rmvb", ".asf", ".f4v",
}

MAX_RESOLVE = 300


def _item(raw: str, path: str, name: str, exists: bool, error: str | None) -> dict:
    return {"input": raw, "path": path, "name": name, "exists": exists, "error": error}


def _clean(raw: str) -> str:
    return raw.strip().strip('"').strip("'")


def classify_path(raw: str) -> dict:
    """单个路径：文件、空文件夹说明，或错误。不展开文件夹。"""
    text = _clean(raw)
    if not text:
        return _item(raw, "", "", False, "路径是空的")
    try:
        path = Path(text).expanduser()
    except (OSError, ValueError):
        return _item(text, "", "", False, "这个路径读不了")
    if not path.is_absolute():
        return _item(text, "", path.name, False, "请填绝对路径，例如 D:\\影片\\a.mp4 或 /home/me/a.mp4")
    try:
        resolved = path.resolve()
    except OSError:
        return _item(text, "", path.name, False, "这个路径读不了")
    if resolved.is_dir():
        return _item(
            text, str(resolved), resolved.name, False,
            "这是文件夹。要加里面的文件，请走「从路径添加」。",
        )
    if not resolved.is_file():
        return _item(text, str(resolved), resolved.name, False, "找不到这个文件")
    return _item(text, str(resolved), resolved.name, True, None)


def expand_directory(raw: str) -> list[dict]:
    """文件夹只列这一层里的音视频。"""
    text = _clean(raw)
    if not text:
        return [_item(raw, "", "", False, "路径是空的")]
    try:
        path = Path(text).expanduser()
    except (OSError, ValueError):
        return [_item(text, "", "", False, "这个路径读不了")]
    if not path.is_absolute():
        return [_item(text, "", path.name, False, "请填绝对路径")]
    try:
        resolved = path.resolve()
    except OSError:
        return [_item(text, "", path.name, False, "这个路径读不了")]
    if not resolved.is_dir():
        one = classify_path(text)
        return [one]
    try:
        children = sorted(resolved.iterdir(), key=lambda p: p.name.lower())
    except OSError:
        return [_item(text, str(resolved), resolved.name, False, "这个文件夹读不了")]
    found: list[dict] = []
    for child in children:
        if not child.is_file():
            continue
        if child.suffix.lower() not in MEDIA_SUFFIXES:
            continue
        if child.name.startswith("."):
            continue
        found.append(_item(str(child), str(child.resolve()), child.name, True, None))
        if len(found) >= MAX_RESOLVE:
            break
    if not found:
        return [_item(text, str(resolved), resolved.name, False, "这个文件夹里没有音视频（只看这一层）")]
    return found


def resolve_local_entries(
    paths: list[str] | None = None,
    directory: str = "",
    names: list[str] | None = None,
    *,
    expand: bool = True,
) -> tuple[list[dict], bool]:
    """核对一批路径。返回 (条目, 是否因为条数上限被截断)。"""
    items: list[dict] = []
    truncated = False

    def push_many(rows: list[dict]) -> None:
        nonlocal truncated
        for row in rows:
            if len(items) >= MAX_RESOLVE:
                truncated = True
                return
            items.append(row)

    for raw in paths or []:
        text = _clean(raw)
        if not text:
            continue
        try:
            candidate = Path(text).expanduser()
            is_dir = candidate.is_absolute() and candidate.expanduser().is_dir()
        except OSError:
            is_dir = False
        rows = expand_directory(text) if expand and is_dir else [classify_path(text)]
        push_many(rows)
        if is_dir and len(rows) >= MAX_RESOLVE:
            truncated = True
        if truncated:
            return items, True

    folder = _clean(directory)
    if folder:
        wanted = [_clean(n) for n in (names or []) if _clean(n)]
        if wanted:
            try:
                base = Path(folder).expanduser()
            except (OSError, ValueError):
                push_many([_item(folder, "", "", False, "这个路径读不了")])
            else:
                if not base.is_absolute():
                    push_many([_item(folder, "", base.name, False, "请填绝对路径")])
                else:
                    for name in wanted:
                        # 只取文件名，避免 name 里夹带 ..\\ 逃出这个文件夹
                        safe = Path(name).name
                        push_many([classify_path(str(base / safe))])
                        if truncated:
                            break
        else:
            push_many(expand_directory(folder))

    return items, truncated
