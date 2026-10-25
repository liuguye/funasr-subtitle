"""本机系统文件窗口。

浏览器里的「选择文件」拿不到绝对路径，同目录写字幕就会落空。
服务跑在用户自己的电脑上时，改由这里弹出系统窗口，把选中的真实路径交回页面。
只应由本机接口调用。
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

from .localfiles import MEDIA_SUFFIXES

_LOCK = threading.Lock()
_DIALOG_TIMEOUT = 30 * 60


class PickerCancelled(Exception):
    """用户关掉了窗口，没有选。"""


class PickerError(Exception):
    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


def parse_picker_output(text: str) -> tuple[str, list[str]]:
    """解析对话框脚本的标准输出。返回 ('ok'|'cancelled', 路径)。"""
    raw = (text or "").lstrip("\ufeff").strip()
    if not raw:
        raise PickerError("系统文件窗口没有返回结果。")
    lines = [line.strip().strip('"') for line in raw.splitlines() if line.strip()]
    head = lines[0].upper()
    if head == "CANCELLED":
        return "cancelled", []
    if head != "OK":
        raise PickerError("系统文件窗口没有返回结果。")
    paths: list[str] = []
    seen: set[str] = set()
    for line in lines[1:]:
        if line and line not in seen:
            seen.add(line)
            paths.append(line)
    return "ok", paths


def _media_filter() -> str:
    globs: list[str] = []
    for suffix in sorted(MEDIA_SUFFIXES):
        body = suffix[1:]
        if suffix.startswith(".") and body.isalnum():
            globs.append(f"*{suffix}")
    return "音视频|" + ";".join(globs) + "|所有文件|*.*"


def _ps_single(text: str) -> str:
    return "'" + text.replace("'", "''") + "'"


def _windows_script(mode: str, result_file: str) -> str:
    """固定脚本。结果路径是我们自己的临时文件，不拼用户输入。"""
    quoted = _ps_single(result_file)
    if mode == "directory":
        dialog = r"""
$dlg = New-Object System.Windows.Forms.FolderBrowserDialog
$dlg.Description = '选择放着音视频的文件夹（只加这一层）'
$dlg.ShowNewFolderButton = $false
"""
        chosen = r"$dlg.SelectedPath"
    else:
        dialog = f"""
$dlg = New-Object System.Windows.Forms.OpenFileDialog
$dlg.Multiselect = $true
$dlg.Title = '选择音视频'
$dlg.Filter = '{_media_filter()}'
$dlg.RestoreDirectory = $true
# 云盘占位 / 重解析点（山鸭 Integrated 等）打开存在性检查时，选完经常拿不到路径。
$dlg.CheckFileExists = $false
$dlg.ValidateNames = $false
$dlg.DereferenceLinks = $true
"""
        chosen = r"$dlg.FileNames"
    return f"""
$ErrorActionPreference = 'Stop'
$utf8 = New-Object System.Text.UTF8Encoding $false
[Console]::OutputEncoding = $utf8
$OutputEncoding = $utf8
Add-Type -AssemblyName System.Windows.Forms
$owner = New-Object System.Windows.Forms.Form
$owner.TopMost = $true
$owner.ShowInTaskbar = $false
$owner.FormBorderStyle = [System.Windows.Forms.FormBorderStyle]::None
$owner.Opacity = 0
$owner.Width = 1
$owner.Height = 1
$owner.StartPosition = [System.Windows.Forms.FormStartPosition]::CenterScreen
$owner.Show()
$owner.Activate()
{dialog}
$result = $dlg.ShowDialog($owner)
$owner.Close()
$lines = New-Object System.Collections.Generic.List[string]
if ($result -eq [System.Windows.Forms.DialogResult]::OK) {{
  [void]$lines.Add('OK')
  foreach ($name in @({chosen})) {{
    if ($name) {{ [void]$lines.Add([string]$name) }}
  }}
}} else {{
  [void]$lines.Add('CANCELLED')
}}
$out = {quoted}
[System.IO.File]::WriteAllLines($out, $lines.ToArray(), $utf8)
foreach ($line in $lines) {{
  [Console]::Out.WriteLine($line)
}}
"""


def read_picker_result(path: Path) -> str:
    """读对话框写下的 UTF-8 结果。顺手认 BOM 和 UTF-16，避免编码看空。"""
    try:
        data = path.read_bytes()
    except OSError:
        return ""
    if not data.strip(b"\x00 \t\r\n"):
        return ""
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        return data.decode("utf-16", errors="replace")
    if b"\x00" in data[:4]:
        try:
            return data.decode("utf-16", errors="replace")
        except UnicodeError:
            pass
    return data.decode("utf-8-sig", errors="replace")


def paths_from_dialog(file_text: str, stdout: str, returncode: int = 0, stderr: str = "") -> list[str]:
    """优先用结果文件。标准输出是空的或编码坏了时，仍能拿到路径。"""
    saw_error: PickerError | None = None
    for text in (file_text, stdout):
        if not (text or "").strip():
            continue
        try:
            return _finish(text, returncode, stderr)
        except PickerCancelled:
            raise
        except PickerError as exc:
            saw_error = exc
    if returncode != 0:
        tail = (stderr or "").strip().splitlines()
        extra = tail[-1][:160] if tail else ""
        message = "系统文件窗口没打开。"
        if extra:
            message = f"{message}（{extra}）"
        raise PickerError(message)
    if saw_error is not None:
        raise saw_error
    raise PickerError("系统文件窗口没有返回结果。")


def _run(argv: list[str], script: str | None = None) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            argv,
            input=script,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=_DIALOG_TIMEOUT,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise PickerError("文件窗口等太久，已关掉。请再选一次。") from exc
    except FileNotFoundError as exc:
        raise PickerError("这台电脑打不开系统文件窗口。") from exc


def _finish(stdout: str, returncode: int, stderr: str) -> list[str]:
    try:
        status, paths = parse_picker_output(stdout)
    except PickerError as exc:
        if returncode != 0:
            tail = (stderr or "").strip().splitlines()
            extra = tail[-1][:160] if tail else ""
            message = "系统文件窗口没打开。"
            if extra:
                message = f"{message}（{extra}）"
            raise PickerError(message) from exc
        raise
    if status == "cancelled":
        raise PickerCancelled()
    return paths


def _open_windows(mode: str) -> list[str]:
    """脚本写 UTF-8 BOM 的 .ps1 再 -File 执行，避免中文 Windows 管道编码丢结果。"""
    fd, name = tempfile.mkstemp(prefix="fs-pick-", suffix=".txt")
    os.close(fd)
    result = Path(name)
    ps1 = result.with_suffix(".ps1")
    try:
        # BOM：powershell -File 在中文系统上按 Unicode 读含「音视频」等中文的脚本
        ps1.write_text(_windows_script(mode, str(result)), encoding="utf-8-sig")
        proc = _run(
            [
                "powershell.exe",
                "-NoProfile",
                "-STA",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(ps1),
            ],
        )
        return paths_from_dialog(read_picker_result(result), proc.stdout, proc.returncode, proc.stderr)
    finally:
        result.unlink(missing_ok=True)
        ps1.unlink(missing_ok=True)


def _open_macos(mode: str) -> list[str]:
    if mode == "directory":
        script = """
try
  set f to POSIX path of (choose folder with prompt "选择放着音视频的文件夹（只加这一层）")
  return "OK" & linefeed & f
on error number -128
  return "CANCELLED"
end try
"""
    else:
        script = """
try
  set picked to choose file with prompt "选择音视频" with multiple selections allowed
  set out to "OK"
  repeat with f in picked
    set out to out & linefeed & POSIX path of f
  end repeat
  return out
on error number -128
  return "CANCELLED"
end try
"""
    proc = _run(["osascript", "-e", script])
    return _finish(proc.stdout, proc.returncode, proc.stderr)


def _open_zenity(zenity: str, mode: str) -> list[str]:
    if mode == "directory":
        cmd = [zenity, "--file-selection", "--directory", "--title=选择文件夹"]
    else:
        cmd = [zenity, "--file-selection", "--multiple", "--separator=\x1f", "--title=选择音视频"]
    proc = _run(cmd)
    if proc.returncode == 1:
        raise PickerCancelled()
    if proc.returncode != 0:
        raise PickerError("系统文件窗口没打开。")
    text = (proc.stdout or "").strip()
    if not text:
        raise PickerCancelled()
    if mode == "directory":
        return [text]
    return [part for part in text.split("\x1f") if part]


def _open_tk(mode: str) -> list[str]:
    try:
        import tkinter as tk
        from tkinter import filedialog
    except Exception as exc:
        raise PickerError("这台电脑打不开系统文件窗口。") from exc
    root = tk.Tk()
    root.withdraw()
    try:
        try:
            root.attributes("-topmost", True)
        except tk.TclError:
            pass
        if mode == "directory":
            chosen = filedialog.askdirectory(title="选择文件夹")
            if not chosen:
                raise PickerCancelled()
            return [str(chosen)]
        patterns = " ".join(f"*{suffix}" for suffix in sorted(MEDIA_SUFFIXES))
        chosen = filedialog.askopenfilenames(
            title="选择音视频",
            filetypes=[("音视频", patterns), ("所有文件", "*.*")],
        )
        if not chosen:
            raise PickerCancelled()
        return [str(path) for path in chosen]
    finally:
        root.destroy()


def _open_linux(mode: str) -> list[str]:
    zenity = shutil.which("zenity")
    if zenity:
        return _open_zenity(zenity, mode)
    return _open_tk(mode)


def _open_dialog(mode: str) -> list[str]:
    if sys.platform == "win32":
        return _open_windows(mode)
    if sys.platform == "darwin":
        return _open_macos(mode)
    return _open_linux(mode)


def pick_media(mode: str) -> list[str]:
    """弹出系统窗口。取消时抛 PickerCancelled，打不开时抛 PickerError。"""
    if mode not in {"files", "directory"}:
        raise PickerError("只能选文件或文件夹。")
    if not _LOCK.acquire(blocking=False):
        raise PickerError("文件窗口已经开着，先在那个窗口里选完或取消。")
    try:
        return _open_dialog(mode)
    finally:
        _LOCK.release()
