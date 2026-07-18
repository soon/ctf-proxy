from ctf_proxy.analytics.context import ConnectionContext, TcpEvent
from ctf_proxy.analytics.rules_seed.tcp_fingerprint import TcpFingerprint


def conn(*reads: str) -> ConnectionContext:
    events = tuple(
        TcpEvent(
            event_type="read", data_text=r, data_size=len(r), end_stream=False, truncated=False
        )
        for r in reads
    )
    return ConnectionContext(
        id=1,
        port=1234,
        connection_id=1,
        start_time=0,
        duration_ms=1,
        bytes_in=0,
        bytes_out=0,
        is_blocked=False,
        batch_id=None,
        events=events,
    )


def match(ctx: ConnectionContext):
    return list(TcpFingerprint().match_tcp(ctx))


def test_same_shape_same_fingerprint():
    a = match(conn("AUTH alice 12345"))
    b = match(conn("AUTH bob 99999"))
    assert a and b
    assert a[0].tag == b[0].tag
    assert a[0].tag.startswith("tcp_fp_")
    assert a[0].meta == "txt AUTH {token} {int}"


def test_different_verb_different_fingerprint():
    a = match(conn("AUTH alice 1"))
    b = match(conn("QUIT alice 1"))
    assert a[0].tag != b[0].tag


def test_empty_connection_yields_nothing():
    assert match(conn()) == []
    assert match(conn("   ")) == []


def test_binary_payload_fingerprints_by_prefix():
    payload = "\x00\x01\x02\xff\xfe"
    result = match(conn(payload))
    assert result
    assert result[0].meta.startswith("bin ")
