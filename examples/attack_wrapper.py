import contextlib
import importlib.util
import io
import re
import sys
from pathlib import Path


def run(exploit_path: Path, flag_regex: str, port_remap: tuple[int, int] | None = None) -> None:
    host = sys.argv[1] if len(sys.argv) > 1 else "127.0.0.1"
    spec = importlib.util.spec_from_file_location("exploit_mod", exploit_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    if port_remap is not None:
        original = module.remote
        src, dst = port_remap
        module.remote = lambda t, port=src, *a, **k: original(t, dst if port == src else port, *a, **k)

    buffer = io.StringIO()
    try:
        with contextlib.redirect_stdout(buffer):
            module.exploit(host)
    except Exception as exc:
        buffer.write(f"\nattack raised: {exc!r}\n")

    out = buffer.getvalue()
    sys.stdout.write(out)
    flags = sorted(set(re.findall(flag_regex, out)))
    if flags:
        print(f"STOLE {len(flags)} flag(s): {flags[:3]}")
        sys.exit(0)
    print("no flag stolen")
    sys.exit(1)
