"""批量 / 本机路径任务。

和 `/api/jobs` 共用同一个队列，只是多接受本机绝对路径，并记下要写到源文件旁边的字幕格式。
浏览器拿不到真实路径时，仍可只上传文件——那样不会写盘，页面里照旧下载。
"""
from __future__ import annotations

import shutil
import uuid
from pathlib import Path

from fastapi import APIRouter, File, Form, Request, UploadFile
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from ..config import MAX_UPLOAD_MB, jobs_dir
from ..media.localfiles import MAX_RESOLVE, classify_path, resolve_local_entries
from ..models import DEFAULT_MODEL_ID
from ..schemas import JobOptions
from ..subtitle import EXPORT_FORMATS

router = APIRouter(prefix="/api")

_LOCAL_CLIENTS = {"127.0.0.1", "::1", "localhost", "testclient"}


def _err(code: str, message: str, status: int = 400, detail: str | None = None) -> JSONResponse:
    body: dict = {"code": code, "message": message}
    if detail:
        body["detail"] = detail
    return JSONResponse(status_code=status, content={"error": body})


def _is_local(request: Request) -> bool:
    client = request.client
    return bool(client) and client.host in _LOCAL_CLIENTS


def _parse_formats(raw: str | None) -> tuple[list[str] | None, JSONResponse | None]:
    """None = 调用方没传，写盘时默认 srt。空字符串 = 明确不写。"""
    if raw is None:
        return None, None
    text = raw.strip()
    if not text:
        return [], None
    chosen: list[str] = []
    for part in text.split(","):
        fmt = part.strip().lower().lstrip(".")
        if not fmt:
            continue
        if fmt not in EXPORT_FORMATS:
            return None, _err("bad_format", f"不支持这种字幕格式：{fmt}", detail=fmt)
        if fmt not in chosen:
            chosen.append(fmt)
    return chosen, None


def _options(
    model_id: str,
    language: str,
    diarization: str,
    hotwords: str,
    use_gpu: str,
    max_chars: int,
    punctuation: str,
) -> JobOptions:
    return JobOptions(
        model_id=model_id or DEFAULT_MODEL_ID,
        language=language if language in {"auto", "zh", "yue", "en", "ja", "ko"} else "auto",
        diarization=str(diarization).lower() in {"true", "1", "yes", "on"},
        hotwords=hotwords or "",
        use_gpu=str(use_gpu).lower() in {"true", "1", "yes", "on"},
        max_chars=max(0, min(100, int(max_chars))),
        punctuation=punctuation if punctuation in {"auto", "on", "off"} else "auto",
    )


def _has_upload(file: UploadFile | None) -> bool:
    return bool(file is not None and (file.filename or "").strip())


async def _discard(file: UploadFile | None) -> None:
    if file is None:
        return
    try:
        while await file.read(1024 * 1024):
            pass
    except Exception:  # noqa: BLE001
        pass
    try:
        await file.close()
    except Exception:  # noqa: BLE001
        pass


async def _save_upload(file: UploadFile) -> tuple[Path, str] | JSONResponse:
    safe_name = Path(file.filename or "input").name or "input"
    dest_dir = jobs_dir() / uuid.uuid4().hex[:12]
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / safe_name
    limit = MAX_UPLOAD_MB * 1024 * 1024 if MAX_UPLOAD_MB > 0 else 0
    written = 0
    try:
        with dest.open("wb") as handle:
            while chunk := await file.read(1024 * 1024):
                written += len(chunk)
                if limit and written > limit:
                    _remove_tree(dest_dir)
                    return _err(
                        "file_too_large",
                        f"文件太大（上限 {MAX_UPLOAD_MB} MB），先切成小段再试",
                        413,
                    )
                handle.write(chunk)
    except Exception:  # noqa: BLE001
        _remove_tree(dest_dir)
        return _err("upload_failed", "文件没传上后台，请重新拖一次", 400)
    return dest, safe_name


def _remove_tree(path: Path) -> None:
    shutil.rmtree(path, ignore_errors=True)


class ResolveBody(BaseModel):
    paths: list[str] = Field(default_factory=list)
    directory: str = ""
    names: list[str] = Field(default_factory=list)
    # 单条路径核对时关掉：文件夹不要展开，避免和「这一行是一个文件」对不齐。
    expand: bool = True


@router.post("/local-media/resolve")
async def resolve_local_media(body: ResolveBody, request: Request):
    """核对绝对路径，或把文件夹展开成这一层的音视频。仅本机客户端。"""
    if not _is_local(request):
        return _err("local_only", "按本机路径读写只允许本机访问。", 403)
    if len(body.paths) + len(body.names) > MAX_RESOLVE:
        return _err("too_many", f"一次最多核对 {MAX_RESOLVE} 个路径。", 400)
    items, truncated = resolve_local_entries(
        body.paths, body.directory, body.names, expand=body.expand,
    )
    return {"items": items, "truncated": truncated}


@router.post("/jobs/local")
async def create_local_job(
    request: Request,
    file: UploadFile | None = File(None),
    source_path: str = Form(""),
    export_formats: str | None = Form(None),
    model_id: str = Form(""),
    language: str = Form("auto"),
    diarization: str = Form("false"),
    hotwords: str = Form(""),
    use_gpu: str = Form("false"),
    max_chars: int = Form(30),
    punctuation: str = Form("auto"),
):
    """上传文件，或直接用本机绝对路径。有路径时完成后把字幕写到该文件旁边。"""
    formats, bad = _parse_formats(export_formats)
    if bad is not None:
        await _discard(file)
        return bad

    raw_path = (source_path or "").strip()
    resolved: Path | None = None
    if raw_path:
        if not _is_local(request):
            await _discard(file)
            return _err("local_only", "按本机路径读写只允许本机访问。", 403)
        info = classify_path(raw_path)
        if not info["exists"]:
            await _discard(file)
            return _err("bad_path", info["error"] or "找不到这个文件", detail=raw_path)
        resolved = Path(info["path"])

    options = _options(model_id, language, diarization, hotwords, use_gpu, max_chars, punctuation)
    mgr = request.app.state.jobs

    if resolved is not None:
        await _discard(file)
        job = mgr.create(
            resolved.name,
            resolved,
            options,
            source_path=resolved,
            owned_input=False,
            export_formats=formats,
        )
        return {"job_id": job.id}

    if not _has_upload(file):
        return _err("no_input", "请选择文件，或填写本机上的绝对路径。")

    assert file is not None
    saved = await _save_upload(file)
    if isinstance(saved, JSONResponse):
        return saved
    dest, safe_name = saved
    job = mgr.create(
        safe_name,
        dest,
        options,
        source_path=None,
        owned_input=True,
        export_formats=formats,
    )
    return {"job_id": job.id}


@router.get("/jobs/{job_id}/outputs")
async def job_outputs(job_id: str, request: Request):
    """字幕写到了哪里。任务还在跑时说明还没写。"""
    mgr = request.app.state.jobs
    job = mgr.get(job_id)
    if not job:
        return _err("not_found", "任务不存在，可能后台已经重启。", 404, detail=job_id)
    meta = getattr(mgr, "output_meta", {}).get(job_id)
    if meta:
        return meta
    if job.status.value == "done":
        return {
            "source_path": None,
            "written_files": [],
            "write_error": None,
            "output_note": "没有本机路径，字幕只留在页面里，可以下载。",
        }
    if job.status.value == "error":
        return {
            "source_path": None,
            "written_files": [],
            "write_error": None,
            "output_note": "转写没完成，没有写字幕。",
        }
    return {
        "source_path": None,
        "written_files": [],
        "write_error": None,
        "output_note": "任务还没完成。",
    }
