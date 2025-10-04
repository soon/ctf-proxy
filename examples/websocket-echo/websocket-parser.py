# websockets >= 14
# requires: websockets >= 14
import base64, re
from typing import Generator, Iterable, Literal, Optional, Tuple, Union
from websockets.frames import Frame, Opcode
from websockets.extensions.permessage_deflate import PerMessageDeflate

_PARAM_RE = re.compile(r';\s*([a-z0-9_\-]+)(?:=([^;,\s]+))?', re.I)

def make_extensions(header: str, is_client: bool) -> Iterable:
    if not header or "permessage-deflate" not in header.lower():
        return []
    params = dict(_PARAM_RE.findall(header.lower()))
    def _bits(v: Optional[str]) -> int: return int(v) if v and v.isdigit() else 15

    # Map client/server params to remote/local by capture direction.
    if is_client:  
        # bytes sent by the client are 'remote'
        remote_nct = "client_no_context_takeover" in params
        local_nct  = "server_no_context_takeover" in params
        remote_wbits = _bits(params.get("client_max_window_bits"))
        local_wbits  = _bits(params.get("server_max_window_bits"))
    else:                   
        # server is 'remote'
        remote_nct = "server_no_context_takeover" in params
        local_nct  = "client_no_context_takeover" in params
        remote_wbits = _bits(params.get("server_max_window_bits"))
        local_wbits  = _bits(params.get("client_max_window_bits"))

    return [PerMessageDeflate(
        remote_no_context_takeover=remote_nct,
        local_no_context_takeover=local_nct,
        remote_max_window_bits=remote_wbits,
        local_max_window_bits=local_wbits,
    )]

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
            return bytes(self.buf[start:self.pos])
        return gen()


def iter_ws_frames_from_b64(
    b64: str,
    *,
    is_client: bool,
    extensions_header: str = "",
    max_size: Optional[int] = None,
) -> Generator[Tuple[bool, Opcode, bytes], None, None]:
    data = base64.b64decode(b64)
    r = FrameReader(data)
    exts = make_extensions(extensions_header, is_client=is_client)

    while r.remaining >= 2:
        try:
            frame = (yield from Frame.parse(
                r.read_exact,
                mask=is_client,
                max_size=max_size,
                extensions=exts,
            ))
        except EOFError:
            break
        yield frame.fin, frame.opcode, bytes(frame.data)

def parse_ws_frames(
    b64: str,
    *,
    is_client: bool,
    extensions_header: str = "",
    max_size: Optional[int] = None,
) -> list[Tuple[bool, Opcode, bytes]]:
    return [
        (fin, opcode, data)
        for fin, opcode, data in iter_ws_frames_from_b64(
                    b64,
        is_client=is_client,
        extensions_header=extensions_header,
        max_size=max_size,
        )
    ]

if __name__ == "__main__":
    # print(parse_ws_frames('wZLyP99/AHcStjto1zC/NREwPHHyLvY/waotIeMfh3fJtgFptq1/calS4+m0zXxxKVIAD61TKiqanziG9vrKC5sa1trKyi8hwZ8gq/FNYgPfhezg9uQOYvXnD+I9YCCh69e7sutXOfHp1Pap8cGYN4b3RHWu24n8SDxr+IVeCX6qvkA+E/cxH1P1RIiCoChJ7KPA',  is_client=True, extensions_header="permessage-deflate; client_max_window_bits=12"))
    # print(parse_ws_frames('wRhyTc7It1LwSM3JyVcIT00Kzk/OTi1RBADBKKpWKqksSFWyUlBKBcor6Sgo5aYWFyemg4UgitOK8nMVvIL9/ZRqAQDBH0KoLsjPSwepLskEqi9JzC0AChqamxkaGhlaGJnWAgDBG0IytqgovwjN3NC87Lz88jwFkBorhVIIT6kWAIgCA+g=',   is_client=False, extensions_header="permessage-deflate; server_max_window_bits=12; client_max_window_bits=12"))

    # print(parse_ws_frames("wZLyP99/AHcStjto1zC/NREwPHHyLvY/waotIeMfh3fJtgFptq1/calS4+m0zXxxKVIAD61TKiqanziG9vrKC5sa1trKyi8hwZ8gq/FNYgPfhezg9uQOYvXnD+I9YCCh69e7sutXOfHp1Pap8cGYN4b3RHWu24n8SDxr+IVeCX6qvkA+E/cxH1P1RIiCoChJ7KPA", is_client=True, extensions_header="permessage-deflate; client_max_window_bits"))
    print(parse_ws_frames("wRhyTc7It1LwSM3JyVcIT00Kzk/OTi1RBADBKKpWKqksSFWyUlBKBcor6Sgo5aYWFyemg4UgitOK8nMVvIL9/ZRqAQDBH0KoLsjPSwepLskEqi9JzC0AChqamxkaGhlaGJnWAgDBG0IytqgovwjN3NC87Lz88jwFkBorhVIIT6kWAIgCA+g=", is_client=False, extensions_header="permessage-deflate; server_max_window_bits=12; client_max_window_bits=12"))