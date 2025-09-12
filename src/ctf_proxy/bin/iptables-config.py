#!/usr/bin/env python3
import os
import shlex
import subprocess
import sys
from pathlib import Path

# ===== Config (override via env) =====
DEFAULT_PORT = int(os.getenv("PORT", "3000"))  # used if PORTS_FILE not set or empty
ENVOY_PORT = int(os.getenv("ENVOY_PORT", "15001"))
ENVOY_UID = int(os.getenv("ENVOY_UID", "1337"))
BRIDGE_IFS = os.getenv("BRIDGE_IFS", "auto")  # space-separated list or "auto"
PROTECT_ENVOY_PORT = os.getenv("PROTECT_ENVOY_PORT", "1") in {"1", "true", "yes", "on"}
ENABLE_IPV6 = os.getenv("ENABLE_IPV6", "auto")  # auto|1|0
IPT = os.getenv("IPT", "iptables")
IP6T = os.getenv("IP6T", "ip6tables")
USER_CHAIN = os.getenv("USER_CHAIN", "ENVOY_PRE")
PORTS_FILE = os.getenv("PORTS_FILE", "").strip()  # path to config with ports


# ===== Utilities =====
def need_root():
    if os.geteuid() != 0:
        print("This script must run as root (use sudo).", file=sys.stderr)
        sys.exit(1)


def have_cmd(cmd: str) -> bool:
    return (
        subprocess.call(
            ["/usr/bin/env", "bash", "-lc", f"command -v {shlex.quote(cmd)} >/dev/null 2>&1"]
        )
        == 0
    )


def ipv6_wanted() -> bool:
    val = str(ENABLE_IPV6).strip().lower()
    if val in {"1", "true", "yes"}:
        return True
    if val in {"0", "false", "no"}:
        return False
    # auto: enable if ip6tables exists
    return have_cmd(IP6T)


def run(cmd: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True)


def rule_exists(ipt: str, table: str, chain: str, args: list[str]) -> bool:
    res = run([ipt, "-t", table, "-C", chain] + args)
    return res.returncode == 0


def chain_exists(ipt: str, table: str, chain: str) -> bool:
    res = run([ipt, "-t", table, "-nL", chain])
    return res.returncode == 0


def ensure_chain(ipt: str, table: str, chain: str):
    if not chain_exists(ipt, table, chain):
        res = run([ipt, "-t", table, "-N", chain])
        if res.returncode != 0:
            raise SystemExit(res.stderr.strip() or f"Failed to create chain {chain} in {table}")


def delete_chain_if_empty(ipt: str, table: str, chain: str):
    if chain_exists(ipt, table, chain):
        # Flush then attempt delete regardless of refcount status
        run([ipt, "-t", table, "-F", chain])
        run([ipt, "-t", table, "-X", chain])


def add_rule_top(ipt: str, table: str, chain: str, args: list[str]):
    if not rule_exists(ipt, table, chain, args):
        res = run([ipt, "-t", table, "-I", chain, "1"] + args)
        if res.returncode != 0:
            raise SystemExit(res.stderr.strip())


def add_rule_end(ipt: str, table: str, chain: str, args: list[str]):
    if not rule_exists(ipt, table, chain, args):
        res = run([ipt, "-t", table, "-A", chain] + args)
        if res.returncode != 0:
            raise SystemExit(res.stderr.strip())


def del_rule(ipt: str, table: str, chain: str, args: list[str]):
    if rule_exists(ipt, table, chain, args):
        run([ipt, "-t", table, "-D", chain] + args)


def detect_bridges() -> list[str]:
    # Find bridge interfaces: docker0, docker_gwbridge, br-*
    res = run(["ip", "-o", "link", "show", "type", "bridge"])
    if res.returncode != 0:
        return []
    names = []
    for line in res.stdout.splitlines():
        try:
            # format: "7: br-abc123: <...>"
            name = line.split(": ", 1)[1].split(":")[0]
        except Exception:
            continue
        if name == "docker0" or name == "docker_gwbridge" or name.startswith("br-"):
            names.append(name)
    return names


def load_ports() -> list[int]:
    ports: list[int] = []
    if PORTS_FILE and Path(PORTS_FILE).is_file():
        text = Path(PORTS_FILE).read_text(encoding="utf-8", errors="ignore")
        # Try YAML first (PyYAML), fall back to regex scanning
        try:
            import yaml  # type: ignore

            data = yaml.safe_load(text)

            # Expect structure like {services: [{port: 3000}, ...]}
            def walk(o):
                if isinstance(o, dict):
                    for k, v in o.items():
                        if str(k).lower() == "port":
                            yield v
                        else:
                            yield from walk(v)
                elif isinstance(o, list):
                    for it in o:
                        yield from walk(it)

            for v in walk(data):
                try:
                    ports.append(int(v))
                except Exception:
                    pass
        except Exception:
            # simple fallback: find lines like "port: 3000"
            import re

            for m in re.finditer(r"(?im)^\s*port\s*:\s*([0-9]{1,5})\s*$", text):
                ports.append(int(m.group(1)))
        ports = sorted({p for p in ports if 1 <= p <= 65535})
    if not ports:
        ports = [DEFAULT_PORT]
    return ports


def setup_family(ipt: str, label: str, ports: list[int], excl_ifs: list[str]):
    print(
        f"[+] ({label}) Setting up NAT redirects via Envoy :{ENVOY_PORT} (UID {ENVOY_UID}) for ports: {', '.join(map(str, ports))}"
    )

    # Create and prepare user chain (one chain handles all target ports)
    ensure_chain(ipt, "nat", USER_CHAIN)

    # Always (re)build USER_CHAIN contents: exclusions then final redirect
    run([ipt, "-t", "nat", "-F", USER_CHAIN])

    # Skip docker/bridge interfaces
    for ifname in excl_ifs:
        add_rule_end(
            ipt,
            "nat",
            USER_CHAIN,
            [
                "-i",
                ifname,
                "-p",
                "tcp",
                "-m",
                "comment",
                "--comment",
                f"envoy: skip on {ifname}",
                "-j",
                "RETURN",
            ],
        )

    # Final redirect to Envoy port
    add_rule_end(
        ipt,
        "nat",
        USER_CHAIN,
        [
            "-p",
            "tcp",
            "-m",
            "comment",
            "--comment",
            f"envoy: redirect to {ENVOY_PORT}",
            "-j",
            "REDIRECT",
            "--to-ports",
            str(ENVOY_PORT),
        ],
    )

    # For each app port: PREROUTING jump and local OUTPUT redirect (excluding Envoy's UID)
    for port in ports:
        add_rule_top(
            ipt,
            "nat",
            "PREROUTING",
            [
                "-p",
                "tcp",
                "--dport",
                str(port),
                "-m",
                "comment",
                "--comment",
                f"envoy: jump to {USER_CHAIN}",
                "-j",
                USER_CHAIN,
            ],
        )
        add_rule_top(
            ipt,
            "nat",
            "OUTPUT",
            [
                "-p",
                "tcp",
                "--dport",
                str(port),
                "-m",
                "addrtype",
                "--dst-type",
                "LOCAL",
                "-m",
                "owner",
                "!",
                "--uid-owner",
                str(ENVOY_UID),
                "-m",
                "comment",
                "--comment",
                f"envoy: local redirect to {ENVOY_PORT}",
                "-j",
                "REDIRECT",
                "--to-ports",
                str(ENVOY_PORT),
            ],
        )

    # Optional: protect Envoy listener from direct remote hits
    if PROTECT_ENVOY_PORT:
        add_rule_top(
            ipt,
            "raw",
            "PREROUTING",
            [
                "!",
                "-i",
                "lo",
                "-p",
                "tcp",
                "--dport",
                str(ENVOY_PORT),
                "-m",
                "comment",
                "--comment",
                f"envoy: drop direct hits to {ENVOY_PORT}",
                "-j",
                "DROP",
            ],
        )

    print(f"[✓] ({label}) Setup complete.")


def teardown_family(ipt: str, label: str, ports: list[int]):
    print(f"[+] ({label}) Tearing down NAT redirects for ports: {', '.join(map(str, ports))}")

    # Remove per-port PREROUTING/OUTPUT rules first to free the user chain
    for port in ports:
        del_rule(
            ipt,
            "nat",
            "PREROUTING",
            [
                "-p",
                "tcp",
                "--dport",
                str(port),
                "-m",
                "comment",
                "--comment",
                f"envoy: jump to {USER_CHAIN}",
                "-j",
                USER_CHAIN,
            ],
        )
        del_rule(
            ipt,
            "nat",
            "OUTPUT",
            [
                "-p",
                "tcp",
                "--dport",
                str(port),
                "-m",
                "addrtype",
                "--dst-type",
                "LOCAL",
                "-m",
                "owner",
                "!",
                "--uid-owner",
                str(ENVOY_UID),
                "-m",
                "comment",
                "--comment",
                f"envoy: local redirect to {ENVOY_PORT}",
                "-j",
                "REDIRECT",
                "--to-ports",
                str(ENVOY_PORT),
            ],
        )

    # Delete the user chain (flush + delete)
    delete_chain_if_empty(ipt, "nat", USER_CHAIN)

    # Remove protection rule (if present)
    if PROTECT_ENVOY_PORT:
        del_rule(
            ipt,
            "raw",
            "PREROUTING",
            [
                "!",
                "-i",
                "lo",
                "-p",
                "tcp",
                "--dport",
                str(ENVOY_PORT),
                "-m",
                "comment",
                "--comment",
                f"envoy: drop direct hits to {ENVOY_PORT}",
                "-j",
                "DROP",
            ],
        )

    print(f"[✓] ({label}) Teardown complete.")


def setup():
    # Resolve bridges once (shared by v4 and v6)
    if BRIDGE_IFS.strip().lower() in {"auto", ""}:
        excl_ifs = detect_bridges()
    else:
        excl_ifs = [x for x in BRIDGE_IFS.split() if x]

    print(
        f"[i] Excluding bridge interfaces from REDIRECT: {(' '.join(excl_ifs)) if excl_ifs else '<none>'}"
    )

    ports = load_ports()
    setup_family(IPT, "IPv4", ports, excl_ifs)
    if ipv6_wanted():
        setup_family(IP6T, "IPv6", ports, excl_ifs)
    else:
        print("[i] IPv6 disabled or unavailable; skipping IPv6 rules.")


def teardown():
    ports = load_ports()
    teardown_family(IPT, "IPv4", ports)
    if ipv6_wanted():
        teardown_family(IP6T, "IPv6", ports)


def usage():
    exe = Path(sys.argv[0]).name
    print(
        f"""Usage: sudo {exe} setup|teardown

Environment overrides:
  PORT={DEFAULT_PORT}
  PORTS_FILE={PORTS_FILE or "<unset>"}   # path to config file listing ports (YAML or text)
  ENVOY_PORT={ENVOY_PORT}
  ENVOY_UID={ENVOY_UID}
  BRIDGE_IFS={BRIDGE_IFS}        # space-separated list or "auto"
  PROTECT_ENVOY_PORT={"1" if PROTECT_ENVOY_PORT else "0"}
  ENABLE_IPV6={ENABLE_IPV6}      # auto|1|0
  IPT={IPT}
  IP6T={IP6T}
  USER_CHAIN={USER_CHAIN}

Notes:
  • If PORTS_FILE is provided, all discovered TCP ports are redirected to :$ENVOY_PORT.
    - YAML example:
        services:
          - name: foo
            port: 3000
          - name: bar
            port: 3001
    - Plain text fallback: any lines like "port: 3000" will be read.
  • If no ports are found in the file, PORT (default {DEFAULT_PORT}) is used.
  • IPv4 and IPv6 traffic to each TCP port is redirected to :$ENVOY_PORT before Docker's DNAT,
    except on excluded bridges.
  • Local traffic (127.0.0.1 and ::1) is redirected too; Envoy's UID is excluded to avoid loops.
  • Direct remote hits to :$ENVOY_PORT are dropped when PROTECT_ENVOY_PORT=1.
""",
        file=sys.stderr,
    )
    sys.exit(2)


def main():
    need_root()
    if len(sys.argv) < 2:
        usage()
    cmd = sys.argv[1]
    if cmd == "setup":
        setup()
    elif cmd == "teardown":
        teardown()
    else:
        usage()


if __name__ == "__main__":
    main()
