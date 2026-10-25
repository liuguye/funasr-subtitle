"""HTTP 监听地址。

默认仍是 127.0.0.1:8765。换端口：

- 环境变量 ``FUNASR_SUBTITLE_PORT``（被占用时，便携入口会往后试 50 个）
- 环境变量 ``FUNASR_SUBTITLE_HOST``（默认 127.0.0.1）
- ``python -m app.main --port 9000 --host 127.0.0.1``
- ``--strict-port`` 或 ``FUNASR_SUBTITLE_STRICT_PORT=1``：指定端口被占用就退出，不顺延

开发时的 uvicorn / Vite 不走这里的顺延，端口以启动参数为准。见仓库根目录 start-dev 脚本。
"""
from __future__ import annotations

import argparse
import os
import socket
import sys
import threading
import webbrowser


class ListenError(Exception):
    """端口或主机不可用。文案可以直接给用户看。"""


def _env(name: str) -> str | None:
    value = os.environ.get(f"FUNASR_SUBTITLE_{name}")
    if value is None or value.strip() == "":
        return None
    return value.strip()


def _truthy(value: str | None) -> bool:
    return bool(value) and value.strip().lower() in {"1", "true", "yes", "on"}


def parse_run_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="funasr-subtitle",
        description="启动 funasr-subtitle 本地服务",
    )
    parser.add_argument(
        "--port", type=int, default=None,
        help="HTTP 端口（默认 8765，或环境变量 FUNASR_SUBTITLE_PORT）",
    )
    parser.add_argument(
        "--host", default=None,
        help="监听地址（默认 127.0.0.1，或环境变量 FUNASR_SUBTITLE_HOST）",
    )
    parser.add_argument(
        "--strict-port", action="store_true",
        help="端口被占用时直接退出，不往后顺延",
    )
    parser.add_argument(
        "--no-browser", action="store_true",
        help="启动后不打开浏览器",
    )
    return parser.parse_args(argv)


def _preferred_port(explicit: int | None) -> int:
    if explicit is not None:
        return explicit
    raw = _env("PORT")
    if raw is None:
        return 8765
    try:
        return int(raw)
    except ValueError as exc:
        raise ListenError(f"FUNASR_SUBTITLE_PORT 不是整数：{raw}") from exc


def _check_port(port: int) -> None:
    if port < 1 or port > 65535:
        raise ListenError("端口要在 1 到 65535 之间")


def _socket_for(host: str) -> socket.socket:
    if ":" in host:
        sock = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
        sock.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 1)
        return sock
    return socket.socket(socket.AF_INET, socket.SOCK_STREAM)


def _can_bind(host: str, port: int) -> bool:
    try:
        with _socket_for(host) as sock:
            sock.bind((host, port))
            return True
    except OSError:
        return False


def _find_free_port(preferred: int, host: str) -> int:
    last = min(preferred + 50, 65536)
    for port in range(preferred, last):
        if _can_bind(host, port):
            return port
    try:
        with _socket_for(host) as sock:
            sock.bind((host, 0))
            return int(sock.getsockname()[1])
    except OSError as exc:
        raise ListenError(f"没有可用端口（从 {preferred} 起）") from exc


def resolve_listen(
    *,
    port: int | None = None,
    host: str | None = None,
    strict: bool = False,
) -> tuple[str, int]:
    """返回 (bind_host, port)。`strict` 或环境变量要求钉死端口时，占用即失败。"""
    bind_host = (host or _env("HOST") or "127.0.0.1").strip() or "127.0.0.1"
    preferred = _preferred_port(port)
    _check_port(preferred)
    pin = strict or _truthy(_env("STRICT_PORT"))
    if pin:
        if not _can_bind(bind_host, preferred):
            raise ListenError(f"端口 {preferred} 已被占用")
        return bind_host, preferred
    return bind_host, _find_free_port(preferred, bind_host)


def browser_host(bind_host: str) -> str:
    """0.0.0.0 / :: 不能拿去开浏览器。"""
    if bind_host in {"0.0.0.0", "::", "::0"}:
        return "127.0.0.1"
    return bind_host


def _open_browser(host: str, port: int, url: str) -> None:
    import time
    for _ in range(40):
        try:
            with socket.create_connection((host, port), timeout=0.25):
                break
        except OSError:
            time.sleep(0.1)
    webbrowser.open(url)


def run_server(app, argv: list[str] | None = None, *, start_tray) -> None:  # noqa: ANN001
    """绑端口、可选托盘和浏览器，然后阻塞跑 uvicorn。"""
    import uvicorn

    args = parse_run_args(sys.argv[1:] if argv is None else argv)
    try:
        host, port = resolve_listen(port=args.port, host=args.host, strict=args.strict_port)
    except ListenError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(2) from exc

    shown = browser_host(host)
    url = f"http://{shown}:{port}"
    print(f"funasr-subtitle  {url}", flush=True)

    config = uvicorn.Config(app, host=host, port=port, log_level="warning")
    server = uvicorn.Server(config)
    app.state._server = server
    start_tray(url, app.state.request_shutdown)
    if not args.no_browser:
        threading.Thread(target=_open_browser, args=(shown, port, url), daemon=True).start()
    server.run()
