import hashlib
import re
import string
from collections.abc import Iterable

from ctf_proxy.analytics.context import ConnectionContext
from ctf_proxy.analytics.rule import Match, PatternRule

UUID_RE = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")
PRINTABLE = set(string.printable)


def infer_type(value: str) -> str:
    if value == "":
        return "empty"
    if re.fullmatch(r"-?\d+", value):
        return "int"
    if re.fullmatch(r"-?\d*\.\d+", value):
        return "float"
    if UUID_RE.fullmatch(value):
        return "uuid"
    if re.fullmatch(r"[0-9a-fA-F]{16,}", value):
        return "hex"
    if re.fullmatch(r"[A-Za-z0-9_.\-]+", value):
        return "token"
    return "string"


def is_texty(text: str) -> bool:
    if not text:
        return False
    printable = sum(1 for c in text if c in PRINTABLE)
    return printable / len(text) >= 0.85


def line_template(line: str) -> str:
    tokens = line.split()
    if not tokens:
        return "empty"
    verb = tokens[0]
    head = verb[:16] if verb.isalpha() else "{" + infer_type(verb) + "}"
    return " ".join([head, *("{" + infer_type(t) + "}" for t in tokens[1:])])


class TcpFingerprint(PatternRule):
    name = "tcp_fingerprint"

    def match_tcp(self, ctx: ConnectionContext) -> Iterable[Match]:
        client = ctx.read_text.strip()
        if not client:
            return
        first_line = client.splitlines()[0][:256]
        if is_texty(first_line):
            schema = "txt " + line_template(first_line)
        else:
            head = ctx.read_text.encode("utf-8", errors="ignore")[:8]
            schema = "bin " + head.hex()
        digest = hashlib.blake2b(schema.encode(), digest_size=6).hexdigest()
        yield Match(tag=f"tcp_fp_{digest}", meta=schema)
