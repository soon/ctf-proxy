import os
import socket

import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


def get_host() -> str:
    return "envoy" if os.getenv("CI") == "true" else "localhost"


def get_base_url() -> str:
    return f"http://{get_host()}:15001"


def request(method: str, path: str, **kwargs):
    base_url = get_base_url()
    url = f"{base_url}{path}"
    return requests.request(method, url, **kwargs)


def https_request(method: str, path: str, **kwargs):
    url = f"https://{get_host()}:15001{path}"
    kwargs.setdefault("verify", False)
    return requests.request(method, url, **kwargs)


def get_tcp_target() -> tuple[str, int]:
    if os.getenv("CI") == "true":
        return "envoy", 15002
    else:
        return "localhost", 15002


def tcp_roundtrip(payload: bytes, recv_timeout: float = 2, connect_timeout: float = 5) -> bytes:
    host, port = get_tcp_target()
    with socket.create_connection((host, port), timeout=connect_timeout) as sock:
        sock.sendall(payload)
        sock.settimeout(recv_timeout)
        chunks: list[bytes] = []
        try:
            while True:
                data = sock.recv(4096)
                if not data:
                    break
                chunks.append(data)
        except TimeoutError:
            pass
        return b"".join(chunks)
