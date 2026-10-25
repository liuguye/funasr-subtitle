"""本机路径解析：批量队列要知道源文件的真实位置，才能把字幕写到旁边。

浏览器里的 File 通常没有绝对路径，所以由本机服务核对用户填的路径。
文件夹只展开一层，避免一次扫进整个磁盘。
"""
from __future__ import annotations

import os
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


_FOLDER = "这是文件夹。要加里面的文件，请用「选择文件夹」。"


def _try_resolve(path: Path) -> Path | None:
    try:
        return path.resolve()
    except OSError:
        return None


def _kind(path: Path) -> str | None:
    """file、dir。stat 失败（云占位常见）则 None。"""
    try:
        if path.is_dir():
            return "dir"
        if path.is_file():
            return "file"
    except OSError:
        return None
    return None


def _can_open(path: Path) -> bool:
    try:
        with path.open("rb"):
            return True
    except OSError:
        return False


def _placeholder_file(path: Path) -> bool:
    """resolve / is_file 失败时，原始绝对路径还在或能打开，就当文件收下。"""
    if _kind(path) == "dir":
        return False
    try:
        if os.path.lexists(path):
            return True
    except OSError:
        pass
    return _can_open(path)


def classify_path(raw: str) -> dict:
    """单个路径：文件、空文件夹说明，或错误。不展开文件夹。

    山鸭 Integrated 这类云占位上，Path.resolve() / is_file() 会失败。
    原始绝对路径还在或能打开时仍接受，字幕才能写到它旁边。
    """
    text = _clean(raw)
    if not text:
        return _item(raw, "", "", False, "路径是空的")
    try:
        path = Path(text).expanduser()
    except (OSError, ValueError):
        return _item(text, "", "", False, "这个路径读不了")
    if not path.is_absolute():
        return _item(text, "", path.name, False, "请填绝对路径，例如 D:\\影片\\a.mp4 或 /home/me/a.mp4")

    resolved = _try_resolve(path)
    if resolved is not None:
        kind = _kind(resolved)
        if kind == "dir":
            return _item(text, str(resolved), resolved.name, False, _FOLDER)
        if kind == "file":
            return _item(text, str(resolved), resolved.name, True, None)

    if _kind(path) == "dir":
        return _item(text, str(path), path.name, False, _FOLDER)
    if _placeholder_file(path):
        return _item(text, str(path), path.name, True, None)
    shown = str(resolved) if resolved is not None else ""
    return _item(text, shown, path.name, False, "找不到这个文件")


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
    resolved = _try_resolve(path)
    folder = resolved if resolved is not None and _kind(resolved) == "dir" else None
    if folder is None and _kind(path) == "dir":
        folder = path
    if folder is None:
        return [classify_path(text)]
    try:
        children = sorted(folder.iterdir(), key=lambda p: p.name.lower())
    except OSError:
        return [_item(text, str(folder), folder.name, False, "这个文件夹读不了")]
    found: list[dict] = []
    for child in children:
        if child.name.startswith("."):
            continue
        if child.suffix.lower() not in MEDIA_SUFFIXES:
            continue
        info = classify_path(str(child))
        if not info["exists"]:
            continue
        found.append(info)
        if len(found) >= MAX_RESOLVE:
            break
    if not found:
        return [_item(text, str(folder), folder.name, False, "这个文件夹里没有音视频（只看这一层）")]
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
            is_dir = candidate.is_absolute() and _kind(candidate) == "dir"
        except (OSError, ValueError):
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
