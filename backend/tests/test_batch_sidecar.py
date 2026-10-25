"""本机路径入队 + 字幕写到源文件旁边。不跑真实 ASR。"""
import tempfile
import time

import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.jobs.batch import BatchJobManager
from app.main import create_app
from app.schemas import JobOptions, Segment
from app.subtitle.sidecar import write_beside


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setenv("FUNASR_SUBTITLE_DATA_DIR", tempfile.mkdtemp(prefix="fs_test_"))
    with TestClient(create_app()) as c:
        yield c


def test_write_beside_uses_source_basename(tmp_path):
    src = tmp_path / "video.mp4"
    src.write_bytes(b"keep-me")
    segs = [Segment(start_ms=0, end_ms=1000, text="你好")]
    written, errors = write_beside(src, segs, ["srt", "vtt", "srt"])
    assert errors == []
    assert src.read_bytes() == b"keep-me"
    srt = (tmp_path / "video.srt").read_text(encoding="utf-8")
    assert srt.startswith("1\n")
    assert "你好" in srt
    assert (tmp_path / "video.vtt").read_text(encoding="utf-8").startswith("WEBVTT")
    assert written == [str(tmp_path / "video.srt"), str(tmp_path / "video.vtt")]


def test_done_hook_writes_next_to_source_and_cleanup_keeps_it(tmp_path, monkeypatch):
    nested = tmp_path / "media"
    nested.mkdir()
    src = nested / "video.mp4"
    src.write_bytes(b"x")

    monkeypatch.setattr(
        "app.jobs.queue.decode_to_16k_mono",
        lambda *args, **kwargs: (np.zeros(16_000, dtype=np.float32), 16_000),
    )

    class _Engine:
        def transcribe(self, wav, sr, options, progress=None, cancel=None):
            return [Segment(start_ms=0, end_ms=1000, text="你好")]

    mgr = BatchJobManager()
    events: list[dict] = []
    mgr.broker.publish = lambda key, event: events.append(event)  # type: ignore[method-assign]
    monkeypatch.setattr(mgr, "_get_engine", lambda *args, **kwargs: _Engine())

    job = mgr.create(
        "video.mp4", src, JobOptions(),
        source_path=src, owned_input=False, export_formats=["srt"],
    )
    mgr._process(job)

    assert (nested / "video.srt").is_file()
    done = next(ev for ev in events if ev.get("type") == "done")
    written = done["job"]["written_files"][0]
    assert str(written).endswith("video.srt")
    assert "你好" in (nested / "video.srt").read_text(encoding="utf-8")
    assert done["job"]["output_note"] == "已写到源文件旁边。"
    assert done["job"]["source_path"] == str(src)

    mgr._cleanup_input(job.id)
    assert src.is_file()
    assert nested.is_dir()
    assert (nested / "video.srt").is_file()


def test_owned_upload_dir_is_still_removed(tmp_path):
    folder = tmp_path / "upload"
    folder.mkdir()
    src = folder / "in.mp4"
    src.write_bytes(b"x")
    mgr = BatchJobManager()
    job = mgr.create("in.mp4", src, JobOptions(), owned_input=True, export_formats=[])
    mgr._cleanup_input(job.id)
    assert not folder.exists()


def test_missing_path_note_when_no_source(tmp_path):
    folder = tmp_path / "upload"
    folder.mkdir()
    src = folder / "in.mp4"
    src.write_bytes(b"x")
    mgr = BatchJobManager()
    job = mgr.create("in.mp4", src, JobOptions(), owned_input=True, export_formats=["srt"])
    job.segments = [Segment(start_ms=0, end_ms=500, text="甲")]
    info = mgr._before_done(job)
    assert info is not None
    assert info["written_files"] == []
    assert "没有本机路径" in info["output_note"]
    assert not (folder / "in.srt").exists()


def test_resolve_and_reject_bad_local_job(client, tmp_path):
    media = tmp_path / "clip.mp4"
    media.write_bytes(b"not-media")
    other = tmp_path / "song.wav"
    other.write_bytes(b"y")
    (tmp_path / "note.txt").write_text("skip", encoding="utf-8")

    listed = client.post("/api/local-media/resolve", json={"paths": [str(tmp_path)]})
    assert listed.status_code == 200
    body = listed.json()
    assert {item["name"] for item in body["items"]} == {"clip.mp4", "song.wav"}
    assert all(item["exists"] for item in body["items"])

    relative = client.post("/api/jobs/local", data={"source_path": "clip.mp4"})
    assert relative.status_code == 400
    assert relative.json()["error"]["code"] == "bad_path"

    missing = client.post("/api/jobs/local", data={"source_path": str(tmp_path / "nope.mp4")})
    assert missing.status_code == 400

    bad_fmt = client.post(
        "/api/jobs/local",
        data={"source_path": str(media), "export_formats": "ass"},
    )
    assert bad_fmt.status_code == 400
    assert bad_fmt.json()["error"]["code"] == "bad_format"

    empty = client.post("/api/jobs/local", data={"language": "zh"})
    assert empty.status_code == 400
    assert empty.json()["error"]["code"] == "no_input"

    created = client.post(
        "/api/jobs/local",
        data={"source_path": str(media), "export_formats": "srt"},
    )
    assert created.status_code == 200, created.text
    job_id = created.json()["job_id"]
    status = None
    for _ in range(80):
        status = client.get(f"/api/jobs/{job_id}").json()["status"]
        if status in {"done", "error"}:
            break
        time.sleep(0.05)
    assert status == "error"
    assert media.is_file()
    assert tmp_path.is_dir()
    # 转写没成功，不应写出半成品字幕
    assert not (tmp_path / "clip.srt").exists()
