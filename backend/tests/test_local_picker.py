"""系统文件窗口：只测解析和接口，不真的弹出对话框。"""
import subprocess
import tempfile
import threading
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.media.localfiles import classify_path, expand_directory
from app.media.picker import (
    PickerCancelled,
    PickerError,
    parse_picker_output,
    paths_from_dialog,
    pick_media,
    read_picker_result,
)


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setenv("FUNASR_SUBTITLE_DATA_DIR", tempfile.mkdtemp(prefix="fs_pick_"))
    with TestClient(create_app()) as c:
        yield c


def test_parse_picker_output_ok():
    status, paths = parse_picker_output("OK\nC:\\影片\\a.mp4\nD:\\b.mkv\n")
    assert status == "ok"
    assert paths == ["C:\\影片\\a.mp4", "D:\\b.mkv"]


def test_parse_picker_output_cancel_and_blank():
    status, paths = parse_picker_output("\ufeffCANCELLED\n")
    assert status == "cancelled"
    assert paths == []
    with pytest.raises(PickerError):
        parse_picker_output("   ")
    with pytest.raises(PickerError):
        parse_picker_output("NOPE\nC:\\a.mp4")


def test_windows_script_stays_fixed():
    from app.media.picker import _windows_script

    files = _windows_script("files", r"C:\temp\fs-pick.txt")
    folder = _windows_script("directory", r"C:\temp\fs-pick.txt")
    assert "Multiselect = $true" in files
    assert "OpenFileDialog" in files
    assert "CheckFileExists = $false" in files
    assert "ValidateNames = $false" in files
    assert "CheckFileExists = $true" not in files
    assert "WriteAllLines" in files
    assert r"C:\temp\fs-pick.txt" in files
    assert "FolderBrowserDialog" in folder
    assert "WriteAllLines" in folder
    assert "Invoke-Expression" not in files
    assert "Invoke-Expression" not in folder
    assert "*.mp4" in files
    assert "选择音视频" in files


def test_empty_stdout_reads_utf8_result_with_chinese(tmp_path):
    result = tmp_path / "picked.txt"
    result.write_text("OK\nD:\\山鸭\\影片.mp4\n", encoding="utf-8")
    text = read_picker_result(result)
    assert "影片.mp4" in text
    assert paths_from_dialog(text, "", 0, "") == ["D:\\山鸭\\影片.mp4"]
    # 标准输出是空的，结果文件才算数。乱码的 stdout 不能盖过文件。
    assert paths_from_dialog("", text, 0, "") == ["D:\\山鸭\\影片.mp4"]
    assert paths_from_dialog(text, "\ufffd\ufffd", 0, "") == ["D:\\山鸭\\影片.mp4"]


def test_empty_dialog_output_is_an_error():
    with pytest.raises(PickerError, match="没有返回结果"):
        paths_from_dialog("", "   ", 0, "")


def test_open_windows_uses_result_file_when_stdout_empty(monkeypatch):
    from app.media.picker import _open_windows

    def fake_run(argv, script=None):
        assert "CheckFileExists = $false" in (script or "")
        assert "ValidateNames = $false" in (script or "")
        marker = "$out = '"
        start = (script or "").find(marker)
        assert start >= 0
        end = script.find("'", start + len(marker))
        out = Path(script[start + len(marker):end])
        out.write_text("OK\nD:\\山鸭\\影片.mp4\nC:\\影片\\b.mkv\n", encoding="utf-8")
        return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")

    monkeypatch.setattr("app.media.picker._run", fake_run)
    assert _open_windows("files") == ["D:\\山鸭\\影片.mp4", "C:\\影片\\b.mkv"]


def test_classify_chinese_and_cloud_placeholder(tmp_path, monkeypatch):
    src = tmp_path / "影片.mp4"
    src.write_bytes(b"x")
    (tmp_path / "说明.txt").write_text("跳过", encoding="utf-8")
    info = classify_path(str(src))
    assert info["exists"] is True
    assert info["name"] == "影片.mp4"
    assert info["path"].endswith("影片.mp4")
    listed = expand_directory(str(tmp_path))
    assert [row["name"] for row in listed] == ["影片.mp4"]

    missing = classify_path(str(tmp_path / "没有.mp4"))
    assert missing["exists"] is False
    assert "找不到" in (missing["error"] or "")

    import app.media.localfiles as localfiles

    real_resolve = localfiles._try_resolve
    real_kind = localfiles._kind
    real_lexists = localfiles.os.path.lexists

    def try_resolve(path: Path):
        if path.name == "云盘.mp4":
            return None
        return real_resolve(path)

    def kind(path: Path):
        if path.name == "云盘.mp4":
            return None
        return real_kind(path)

    def lexists(path):
        if Path(path).name == "云盘.mp4":
            return True
        return real_lexists(path)

    monkeypatch.setattr(localfiles, "_try_resolve", try_resolve)
    monkeypatch.setattr(localfiles, "_kind", kind)
    monkeypatch.setattr(localfiles.os.path, "lexists", lexists)
    held = classify_path(str(tmp_path / "云盘.mp4"))
    assert held["exists"] is True
    assert held["name"] == "云盘.mp4"
    assert held["path"].endswith("云盘.mp4")
    assert held["error"] is None


def test_classify_accepts_path_that_can_only_be_opened(tmp_path, monkeypatch):
    import app.media.localfiles as localfiles

    monkeypatch.setattr(localfiles, "_try_resolve", lambda path: None)
    monkeypatch.setattr(localfiles, "_kind", lambda path: None)
    monkeypatch.setattr(localfiles.os.path, "lexists", lambda path: False)
    monkeypatch.setattr(localfiles, "_can_open", lambda path: path.name == "只读打开.mp4")
    opened = classify_path(str(tmp_path / "只读打开.mp4"))
    assert opened["exists"] is True
    assert opened["path"].endswith("只读打开.mp4")
    rejected = classify_path(str(tmp_path / "打不开.mp4"))
    assert rejected["exists"] is False


def test_pick_refuses_second_dialog(monkeypatch):
    started = threading.Event()
    release = threading.Event()

    def hang(mode: str) -> list[str]:
        started.set()
        assert release.wait(3)
        return [mode]

    monkeypatch.setattr("app.media.picker._open_dialog", hang)
    box: dict = {}

    def run():
        try:
            box["paths"] = pick_media("files")
        except Exception as exc:  # noqa: BLE001
            box["err"] = exc

    worker = threading.Thread(target=run)
    worker.start()
    assert started.wait(2)
    with pytest.raises(PickerError, match="已经开着"):
        pick_media("directory")
    release.set()
    worker.join(3)
    assert box["paths"] == ["files"]
    assert "err" not in box


def test_pick_route_returns_paths(client, monkeypatch):
    def fake_pick(mode: str) -> list[str]:
        if mode == "files":
            return [r"C:\media\a.mp4"]
        return [r"C:\media"]

    monkeypatch.setattr("app.api.batch.pick_media", fake_pick)

    chosen = client.post("/api/local-media/pick", json={"mode": "files"})
    assert chosen.status_code == 200
    assert chosen.json() == {
        "paths": [r"C:\media\a.mp4"],
        "cancelled": False,
        "truncated": False,
    }

    folder = client.post("/api/local-media/pick", json={"mode": "directory"})
    assert folder.json()["paths"] == [r"C:\media"]


def test_pick_route_cancel_unavailable_and_rejected(client, monkeypatch):
    def cancelled(mode: str):
        raise PickerCancelled()

    monkeypatch.setattr("app.api.batch.pick_media", cancelled)
    res = client.post("/api/local-media/pick", json={"mode": "files"})
    assert res.status_code == 200
    assert res.json()["cancelled"] is True
    assert res.json()["paths"] == []

    def unavailable(mode: str):
        raise PickerError("打不开")

    monkeypatch.setattr("app.api.batch.pick_media", unavailable)
    res = client.post("/api/local-media/pick", json={})
    assert res.status_code == 503
    assert res.json()["error"]["code"] == "picker_unavailable"

    res = client.post("/api/local-media/pick", json={"mode": "nope"})
    assert res.status_code == 400
    assert res.json()["error"]["code"] == "bad_mode"

    monkeypatch.setattr("app.api.batch._is_local", lambda request: False)
    res = client.post("/api/local-media/pick", json={"mode": "files"})
    assert res.status_code == 403
    assert res.json()["error"]["code"] == "local_only"
