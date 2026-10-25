"""端口选择：换端口、钉死端口、占用时顺延。不真正拉起 uvicorn。"""
import socket

import pytest

from app.runtime.listen import ListenError, browser_host, parse_run_args, resolve_listen


def _busy_port() -> tuple[socket.socket, int]:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    return sock, sock.getsockname()[1]


def test_parse_flags():
    args = parse_run_args(["--port", "9321", "--host", "127.0.0.1", "--strict-port", "--no-browser"])
    assert args.port == 9321
    assert args.host == "127.0.0.1"
    assert args.strict_port is True
    assert args.no_browser is True


def test_explicit_free_port_is_kept():
    sock, port = _busy_port()
    sock.close()
    host, got = resolve_listen(port=port, host="127.0.0.1", strict=True)
    assert host == "127.0.0.1"
    assert got == port


def test_strict_port_refuses_when_busy():
    sock, port = _busy_port()
    try:
        with pytest.raises(ListenError, match="已被占用"):
            resolve_listen(port=port, host="127.0.0.1", strict=True)
    finally:
        sock.close()


def test_scan_skips_busy_port():
    sock, port = _busy_port()
    try:
        _host, got = resolve_listen(port=port, host="127.0.0.1", strict=False)
        assert got != port
        assert port < got <= port + 50
    finally:
        sock.close()


def test_bad_port_and_env(monkeypatch):
    with pytest.raises(ListenError):
        resolve_listen(port=0, host="127.0.0.1", strict=True)
    monkeypatch.setenv("FUNASR_SUBTITLE_PORT", "nope")
    with pytest.raises(ListenError):
        resolve_listen(host="127.0.0.1")
    monkeypatch.setenv("FUNASR_SUBTITLE_PORT", "8765")
    monkeypatch.setenv("FUNASR_SUBTITLE_STRICT_PORT", "1")
    # 8765 在这台机器上可能空着也可能被占；只要求 strict 环境变量会被读到，
    # 用一个刚占住的端口验证它不会顺延。
    sock, port = _busy_port()
    try:
        with pytest.raises(ListenError):
            resolve_listen(port=port, host="127.0.0.1", strict=False)
    finally:
        sock.close()


def test_browser_host_rewrites_wildcard():
    assert browser_host("0.0.0.0") == "127.0.0.1"
    assert browser_host("127.0.0.1") == "127.0.0.1"
