from common import tcp_roundtrip


def test_tcp_passthrough():
    response = tcp_roundtrip(b"hello tcp\n")
    assert response == b"hello tcp\n"


def test_tcp_passthrough_without_marker():
    response = tcp_roundtrip(b"just some data\n")
    assert response == b"just some data\n"


def test_tcp_blocked_on_marker():
    response = tcp_roundtrip(b"BLOCK this\n")
    assert response == b""


def test_tcp_blocked_marker_as_substring():
    response = tcp_roundtrip(b"prefix-BLOCK-suffix\n")
    assert response == b""
