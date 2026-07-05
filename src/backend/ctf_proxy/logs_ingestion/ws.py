import base64
import re
from collections.abc import Generator, Iterable

from websockets.extensions.permessage_deflate import PerMessageDeflate
from websockets.frames import Frame, Opcode

_PARAM_RE = re.compile(r";\s*([a-z0-9_\-]+)(?:=([^;,\s]+))?", re.I)


def make_extensions(header: str, is_client: bool) -> Iterable:
    if not header or "permessage-deflate" not in header.lower():
        return []
    params = dict(_PARAM_RE.findall(header.lower()))

    def _bits(v: str | None) -> int:
        return int(v) if v and v.isdigit() else 15

    # Map client/server params to remote/local by capture direction.
    if is_client:
        # bytes sent by the client are 'remote'
        remote_nct = "client_no_context_takeover" in params
        local_nct = "server_no_context_takeover" in params
        remote_wbits = _bits(params.get("client_max_window_bits"))
        local_wbits = _bits(params.get("server_max_window_bits"))
    else:
        # server is 'remote'
        remote_nct = "server_no_context_takeover" in params
        local_nct = "client_no_context_takeover" in params
        remote_wbits = _bits(params.get("server_max_window_bits"))
        local_wbits = _bits(params.get("client_max_window_bits"))

    return [
        PerMessageDeflate(
            remote_no_context_takeover=remote_nct,
            local_no_context_takeover=local_nct,
            remote_max_window_bits=remote_wbits,
            local_max_window_bits=local_wbits,
        )
    ]


class FrameReader:
    def __init__(self, buf: bytes):
        self.buf = buf
        self.pos = 0

    @property
    def remaining(self) -> int:
        return len(self.buf) - self.pos

    def read_exact(self, n: int):
        def gen():
            if self.pos + n > len(self.buf):
                raise EOFError
            start = self.pos
            self.pos += n
            if False:  # keep as generator
                yield None
            return bytes(self.buf[start : self.pos])

        return gen()


def iter_ws_frames_from_b64(
    b64: str,
    *,
    is_client: bool,
    extensions_header: str = "",
    max_size: int | None = None,
) -> Generator[tuple[bool, Opcode, bytes]]:
    data = base64.b64decode(b64)
    r = FrameReader(data)
    exts = make_extensions(extensions_header, is_client=is_client)

    while r.remaining >= 2:
        try:
            frame = yield from Frame.parse(
                r.read_exact,
                mask=is_client,
                max_size=max_size,
                extensions=exts,
            )
        except EOFError:
            break
        yield frame.fin, frame.opcode, bytes(frame.data)


def parse_ws_frames(
    b64: str,
    *,
    is_client: bool,
    extensions_header: str = "",
    max_size: int | None = None,
) -> list[tuple[bool, Opcode, bytes]]:
    return [
        (fin, opcode, data)
        for fin, opcode, data in iter_ws_frames_from_b64(
            b64,
            is_client=is_client,
            extensions_header=extensions_header,
            max_size=max_size,
        )
    ]
