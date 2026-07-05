import hashlib
import json
import re
from collections.abc import Iterable
from urllib.parse import parse_qsl

from ctf_proxy.analytics.context import RequestContext
from ctf_proxy.analytics.rule import Match, PatternRule

UUID_RE = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")


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


def norm_segment(segment: str) -> str:
    if not segment:
        return segment
    if re.fullmatch(r"\d+", segment):
        return "{num}"
    if UUID_RE.fullmatch(segment):
        return "{uuid}"
    if re.fullmatch(r"[0-9a-fA-F]{16,}", segment):
        return "{hex}"
    if re.fullmatch(r"[A-Za-z0-9_.\-]+", segment):
        if len(segment) >= 12 and re.search(r"\d", segment):
            return "{id}"
        return segment
    return "{str}"


def path_template(path: str) -> str:
    return "/".join(norm_segment(s) for s in path.split("/"))


def query_schema(query: str) -> list[str]:
    schema = {name: infer_type(value) for name, value in parse_qsl(query, keep_blank_values=True)}
    return [f"{name}:{schema[name]}" for name in sorted(schema)]


def json_value_type(value: object) -> str:
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, int):
        return "int"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return infer_type(value)
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return "null"


def body_schema(body: str | None) -> str:
    if not body:
        return ""
    stripped = body.lstrip()
    if stripped[:1] in ("{", "["):
        try:
            parsed = json.loads(stripped)
        except ValueError:
            return "json?"
        if isinstance(parsed, dict):
            fields = ",".join(f"{k}:{json_value_type(v)}" for k, v in sorted(parsed.items()))
            return "{" + fields + "}"
        return "[array]"
    if "=" in stripped and "\n" not in stripped[:200]:
        schema = {name: infer_type(value) for name, value in parse_qsl(stripped, keep_blank_values=True)}
        if schema:
            return "form(" + ",".join(f"{k}:{schema[k]}" for k in sorted(schema)) + ")"
    return f"raw:{infer_type(stripped[:64])}"


class RequestFingerprint(PatternRule):
    name = "request_fingerprint"

    def match(self, ctx: RequestContext) -> Iterable[Match]:
        raw_path, _, query = ctx.path.partition("?")
        parts = [f"{ctx.method} {path_template(raw_path)}"]
        qs = query_schema(query)
        if qs:
            parts.append("?" + ",".join(qs))
        bs = body_schema(ctx.body)
        if bs:
            parts.append("#" + bs)
        schema = " ".join(parts)
        digest = hashlib.blake2b(schema.encode(), digest_size=6).hexdigest()
        yield Match(tag=f"fp_{digest}", meta=schema)
