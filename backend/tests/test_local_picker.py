"""系统文件窗口：只测解析和接口，不真的弹出对话框。"""
import tempfile
import threading

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.media.picker import PickerCancelled, PickerError, parse_picker_output, pick_media


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

    files = _windows_script("files")
    folder = _windows_script("directory")
    assert "Multiselect = $true" in files
    assert "OpenFileDialog" in files
    assert "FolderBrowserDialog" in folder
    assert "Invoke-Expression" not in files
    assert "Invoke-Expression" not in folder
    assert "*.mp4" in files
    assert "选择音视频" in files


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
