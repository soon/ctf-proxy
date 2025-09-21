#!/usr/bin/env python3
"""
CTF Proxy iptables configuration utility.

Manages transparent traffic interception by setting up REDIRECT rules to forward
TCP traffic from configured service ports to an Envoy proxy. Handles both IPv4/IPv6,
excludes Docker bridge interfaces, and prevents direct access to the Envoy listener.

Traffic Flow (for HTTP port 3000 example, similar for TCP):
┌──────────────┐    ┌──────────────┐    ┌─────────┐    ┌───────────────┐    ┌─────────┐
│ Client       │───▶│ iptables     │───▶│ Envoy   │───▶│ iptables      │───▶│ Service │
│ :any → :3000 │    │ REDIRECT     │    │ :15001  │    │ UID BYPASS    │    │ :3000   │
└──────────────┘    │ :3000→:15001 │    └─────────┘    │ (no redirect) │    └─────────┘
                    └──────────────┘                   └───────────────┘

Rule Structure:
PREROUTING: tcp --dport 3000 → jump ENVOY_PRE
OUTPUT:     tcp --dport 3000 → REDIRECT :15001 (exclude Envoy UID)
ENVOY_PRE:  -i docker0 → RETURN
            -i br-*    → RETURN
            *          → REDIRECT :15001
raw/PREROUTING: !-i lo tcp --dport 15001 → DROP (protection)

Key operations:
- setup/teardown: bulk configuration from YAML config file
- add-port/remove-port: per-port management for dynamic services
- info: display current iptables state

Uses a custom chain (ENVOY_PRE) for centralized rule management and avoids
redirect loops by excluding Envoy's UID from OUTPUT rules.
"""

import os
import shlex
import subprocess
import sys
from pathlib import Path

import yaml

# ===== Config (override via env) =====
ENVOY_HTTP_PORT = int(os.getenv("ENVOY_HTTP_PORT", "15001"))
ENVOY_TCP_PORT = int(os.getenv("ENVOY_TCP_PORT", "15002"))
ENVOY_UID = int(os.getenv("ENVOY_UID", "1337"))
BRIDGE_IFS = os.getenv("BRIDGE_IFS", "auto")  # space-separated list or "auto"
PROTECT_ENVOY_PORT = os.getenv("PROTECT_ENVOY_PORT", "1") in {"1", "true", "yes", "on"}
ENABLE_IPV6 = os.getenv("ENABLE_IPV6", "auto")  # auto|1|0
IPT = os.getenv("IPT", "iptables")
IP6T = os.getenv("IP6T", "ip6tables")
USER_CHAIN_HTTP = os.getenv("USER_CHAIN_HTTP", "ENVOY_HTTP")
USER_CHAIN_TCP = os.getenv("USER_CHAIN_TCP", "ENVOY_TCP")
PORTS_FILE = os.getenv("PORTS_FILE", "data/config.yml").strip()  # path to config with ports


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
    if val == "auto":
        return have_cmd(IP6T)
    return val in {"1", "true", "yes"}


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


def load_ports() -> tuple[list[int], list[int]]:
    """Load ports from config file and return (http_ports, tcp_ports)."""
    http_ports: list[int] = []
    tcp_ports: list[int] = []

    if PORTS_FILE and Path(PORTS_FILE).is_file():
        text = Path(PORTS_FILE).read_text(encoding="utf-8", errors="ignore")
        data = yaml.safe_load(text)

        # Parse services from YAML
        services = data.get("services", []) if isinstance(data, dict) else []
        for service in services:
            if isinstance(service, dict):
                port = service.get("port")
                service_type = service.get("type", "http").lower()

                if port:
                    try:
                        port = int(port)
                        if 1 <= port <= 65535:
                            if service_type in ["http", "https", "ws", "wss"]:
                                http_ports.append(port)
                            else:  # tcp, udp, etc.
                                tcp_ports.append(port)
                    except (ValueError, TypeError):
                        pass

        http_ports = sorted(set(http_ports))
        tcp_ports = sorted(set(tcp_ports))

    if not http_ports and not tcp_ports:
        raise ValueError(f"No valid ports found (tried {PORTS_FILE})")

    return http_ports, tcp_ports


def setup_family(
    ipt: str, label: str, http_ports: list[int], tcp_ports: list[int], excl_ifs: list[str]
):
    print(f"[+] ({label}) Setting up NAT redirects via Envoy (UID {ENVOY_UID})")
    if http_ports:
        print(f"    HTTP ports (→ :{ENVOY_HTTP_PORT}): {', '.join(map(str, http_ports))}")
    if tcp_ports:
        print(f"    TCP ports  (→ :{ENVOY_TCP_PORT}): {', '.join(map(str, tcp_ports))}")

    # Create and prepare user chains for HTTP and TCP
    if http_ports:
        ensure_chain(ipt, "nat", USER_CHAIN_HTTP)
        run([ipt, "-t", "nat", "-F", USER_CHAIN_HTTP])

        # Skip docker/bridge interfaces for HTTP
        for ifname in excl_ifs:
            add_rule_end(
                ipt,
                "nat",
                USER_CHAIN_HTTP,
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

        # Final redirect to HTTP Envoy port
        add_rule_end(
            ipt,
            "nat",
            USER_CHAIN_HTTP,
            [
                "-p",
                "tcp",
                "-m",
                "comment",
                "--comment",
                f"envoy: redirect to {ENVOY_HTTP_PORT}",
                "-j",
                "REDIRECT",
                "--to-ports",
                str(ENVOY_HTTP_PORT),
            ],
        )

    if tcp_ports:
        ensure_chain(ipt, "nat", USER_CHAIN_TCP)
        run([ipt, "-t", "nat", "-F", USER_CHAIN_TCP])

        # Skip docker/bridge interfaces for TCP
        for ifname in excl_ifs:
            add_rule_end(
                ipt,
                "nat",
                USER_CHAIN_TCP,
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

        # Final redirect to TCP Envoy port
        add_rule_end(
            ipt,
            "nat",
            USER_CHAIN_TCP,
            [
                "-p",
                "tcp",
                "-m",
                "comment",
                "--comment",
                f"envoy: redirect to {ENVOY_TCP_PORT}",
                "-j",
                "REDIRECT",
                "--to-ports",
                str(ENVOY_TCP_PORT),
            ],
        )

    # For each HTTP port: PREROUTING jump and local OUTPUT redirect
    for port in http_ports:
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
                f"envoy: jump to {USER_CHAIN_HTTP}",
                "-j",
                USER_CHAIN_HTTP,
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
                f"envoy: local redirect to {ENVOY_HTTP_PORT}",
                "-j",
                "REDIRECT",
                "--to-ports",
                str(ENVOY_HTTP_PORT),
            ],
        )

    # For each TCP port: PREROUTING jump and local OUTPUT redirect
    for port in tcp_ports:
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
                f"envoy: jump to {USER_CHAIN_TCP}",
                "-j",
                USER_CHAIN_TCP,
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
                f"envoy: local redirect to {ENVOY_TCP_PORT}",
                "-j",
                "REDIRECT",
                "--to-ports",
                str(ENVOY_TCP_PORT),
            ],
        )

    # Optional: protect Envoy listeners from direct remote hits
    if PROTECT_ENVOY_PORT:
        for port in [ENVOY_HTTP_PORT, ENVOY_TCP_PORT]:
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
                    str(port),
                    "-m",
                    "comment",
                    "--comment",
                    f"envoy: drop direct hits to {port}",
                    "-j",
                    "DROP",
                ],
            )

    print(f"[✓] ({label}) Setup complete.")


def teardown_family(ipt: str, label: str, http_ports: list[int], tcp_ports: list[int]):
    all_ports = http_ports + tcp_ports
    print(f"[+] ({label}) Tearing down NAT redirects for ports: {', '.join(map(str, all_ports))}")

    # Remove HTTP port rules
    for port in http_ports:
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
                f"envoy: jump to {USER_CHAIN_HTTP}",
                "-j",
                USER_CHAIN_HTTP,
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
                f"envoy: local redirect to {ENVOY_HTTP_PORT}",
                "-j",
                "REDIRECT",
                "--to-ports",
                str(ENVOY_HTTP_PORT),
            ],
        )

    # Remove TCP port rules
    for port in tcp_ports:
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
                f"envoy: jump to {USER_CHAIN_TCP}",
                "-j",
                USER_CHAIN_TCP,
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
                f"envoy: local redirect to {ENVOY_TCP_PORT}",
                "-j",
                "REDIRECT",
                "--to-ports",
                str(ENVOY_TCP_PORT),
            ],
        )

    # Delete the user chains (flush + delete)
    delete_chain_if_empty(ipt, "nat", USER_CHAIN_HTTP)
    delete_chain_if_empty(ipt, "nat", USER_CHAIN_TCP)

    # Remove protection rules (if present)
    if PROTECT_ENVOY_PORT:
        for port in [ENVOY_HTTP_PORT, ENVOY_TCP_PORT]:
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
                    str(port),
                    "-m",
                    "comment",
                    "--comment",
                    f"envoy: drop direct hits to {port}",
                    "-j",
                    "DROP",
                ],
            )

    print(f"[✓] ({label}) Teardown complete.")


def add_port_family(ipt: str, label: str, port: int, port_type: str, excl_ifs: list[str]):
    print(f"[+] ({label}) Adding NAT redirect for port {port}")

    if port_type == "http":
        USER_CHAIN = USER_CHAIN_HTTP
        ENVOY_PORT = ENVOY_HTTP_PORT
    else:
        USER_CHAIN = USER_CHAIN_TCP
        ENVOY_PORT = ENVOY_TCP_PORT

    # Ensure user chain exists (create it if needed)
    ensure_chain(ipt, "nat", USER_CHAIN)

    # Check if user chain has the final redirect rule, add if missing
    final_redirect_args = [
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
    ]
    if not rule_exists(ipt, "nat", USER_CHAIN, final_redirect_args):
        # First, add exclusions for bridge interfaces
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
        # Then add the final redirect rule
        add_rule_end(ipt, "nat", USER_CHAIN, final_redirect_args)

    # Add PREROUTING jump for this port
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

    # Add OUTPUT redirect for this port (excluding Envoy's UID)
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

    # Add protection rule if enabled and not already present
    if PROTECT_ENVOY_PORT:
        protection_args = [
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
        ]
        add_rule_top(ipt, "raw", "PREROUTING", protection_args)

    print(f"[✓] ({label}) Port {port} redirect added.")


def remove_port_family(ipt: str, label: str, port: int, port_type: str):
    print(f"[+] ({label}) Removing NAT redirect for port {port}")

    if port_type == "http":
        USER_CHAIN = USER_CHAIN_HTTP
        ENVOY_PORT = ENVOY_HTTP_PORT
    elif port_type == "tcp":
        USER_CHAIN = USER_CHAIN_TCP
        ENVOY_PORT = ENVOY_TCP_PORT
    else:
        raise ValueError(f"Unknown port type: {port_type}")

    # Remove PREROUTING rule for this port
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

    # Remove OUTPUT rule for this port
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

    print(f"[✓] ({label}) Port {port} redirect removed.")


def add_port(port: int):
    http_ports, tcp_ports = load_ports()
    if port in http_ports:
        port_type = "http"
    elif port in tcp_ports:
        port_type = "tcp"
    else:
        raise ValueError(f"Port {port} not found in configuration")

    # Resolve bridges
    if BRIDGE_IFS.strip().lower() in {"auto", ""}:
        excl_ifs = detect_bridges()
    else:
        excl_ifs = [x for x in BRIDGE_IFS.split() if x]

    add_port_family(IPT, "IPv4", port, port_type, excl_ifs)
    if ipv6_wanted():
        add_port_family(IP6T, "IPv6", port, port_type, excl_ifs)
    else:
        print("[i] IPv6 disabled or unavailable; skipping IPv6 rules.")


def remove_port(port: int):
    http_ports, tcp_ports = load_ports()
    if port in http_ports:
        port_type = "http"
    elif port in tcp_ports:
        port_type = "tcp"
    else:
        raise ValueError(f"Port {port} not found in configuration")

    remove_port_family(IPT, "IPv4", port, port_type)
    if ipv6_wanted():
        remove_port_family(IP6T, "IPv6", port, port_type)


def cleanup_old_chains(ipt: str):
    """Remove old ENVOY_PRE chain if it exists from previous setup."""
    old_chain = "ENVOY_PRE"
    if chain_exists(ipt, "nat", old_chain):
        print(f"[i] Cleaning up old chain '{old_chain}' from previous setup...")

        # Remove any rules that jump to the old chain
        res = run([ipt, "-t", "nat", "-nL", "PREROUTING"])
        if res.returncode == 0:
            for line in res.stdout.splitlines():
                if old_chain in line:
                    # Try to remove rules jumping to old chain
                    run([ipt, "-t", "nat", "-D", "PREROUTING", "-j", old_chain])

        res = run([ipt, "-t", "nat", "-nL", "OUTPUT"])
        if res.returncode == 0:
            for line in res.stdout.splitlines():
                if old_chain in line:
                    # Try to remove rules jumping to old chain
                    run([ipt, "-t", "nat", "-D", "OUTPUT", "-j", old_chain])

        # Flush and delete the old chain
        run([ipt, "-t", "nat", "-F", old_chain])
        run([ipt, "-t", "nat", "-X", old_chain])
        print(f"[✓] Old chain '{old_chain}' removed.")


def setup():
    # Clean up old chains from previous setup
    cleanup_old_chains(IPT)
    if ipv6_wanted():
        cleanup_old_chains(IP6T)

    # Resolve bridges once (shared by v4 and v6)
    if BRIDGE_IFS.strip().lower() in {"auto", ""}:
        excl_ifs = detect_bridges()
    else:
        excl_ifs = [x for x in BRIDGE_IFS.split() if x]

    print(
        f"[i] Excluding bridge interfaces from REDIRECT: {(' '.join(excl_ifs)) if excl_ifs else '<none>'}"
    )

    http_ports, tcp_ports = load_ports()
    setup_family(IPT, "IPv4", http_ports, tcp_ports, excl_ifs)
    if ipv6_wanted():
        setup_family(IP6T, "IPv6", http_ports, tcp_ports, excl_ifs)
    else:
        print("[i] IPv6 disabled or unavailable; skipping IPv6 rules.")


def teardown():
    http_ports, tcp_ports = load_ports()
    teardown_family(IPT, "IPv4", http_ports, tcp_ports)
    if ipv6_wanted():
        teardown_family(IP6T, "IPv6", http_ports, tcp_ports)

    # Also clean up old chains if they exist
    cleanup_old_chains(IPT)
    if ipv6_wanted():
        cleanup_old_chains(IP6T)


def parse_iptables_rule(line: str) -> dict:
    """Parse an iptables rule line and extract structured information."""
    import re

    # Extract comment if present
    comment_match = re.search(r"/\*\s*([^*]+)\s*\*/", line)
    comment = comment_match.group(1).strip() if comment_match else ""

    # Extract comment text after "envoy: "
    comment_text = ""
    if "envoy:" in comment:
        comment_text = comment.split("envoy:", 1)[1].strip()

    # Split line into parts
    parts = line.split()
    if len(parts) < 6:
        return {"raw": line, "comment": comment_text, "interface": "", "condition": ""}

    # Parse basic fields
    rule_info = {
        "num": parts[0] if parts[0].isdigit() else "",
        "target": parts[1] if len(parts) > 1 else "",
        "prot": parts[2] if len(parts) > 2 else "",
        "opt": parts[3] if len(parts) > 3 else "",
        "source": parts[4] if len(parts) > 4 else "",
        "destination": parts[5] if len(parts) > 5 else "",
        "condition": " ".join(parts[6:]) if len(parts) > 6 else "",
        "comment": comment_text,
        "interface": "",
        "raw": line,
    }

    # Clean up condition (remove comment part)
    if comment:
        rule_info["condition"] = rule_info["condition"].replace(f"/* {comment} */", "").strip()

    # Extract interface from the comment first (more reliable for our rules)
    # Look for "skip on <interface>" or similar patterns in the comment
    if comment_text:
        interface_from_comment = re.search(r"skip on (\S+)", comment_text)
        if interface_from_comment:
            rule_info["interface"] = interface_from_comment.group(1)

    # If no interface found in comment, try to parse from condition
    # Look for patterns like "-i docker0" or "!-i lo" in the condition
    if not rule_info["interface"]:
        interface_match = re.search(r"(?:^|\s)(?:!)?-i\s+(\S+)", rule_info["condition"])
        if interface_match:
            rule_info["interface"] = interface_match.group(1)

    # Also check if there's an interface field in the iptables output itself
    # Sometimes iptables shows interface in a separate column
    if not rule_info["interface"] and len(parts) > 6:
        # Look for interface patterns in the parts
        for part in parts:
            if part in ["docker0", "br-*"] or part.startswith("br-") or part == "lo":
                rule_info["interface"] = part
                break

    return rule_info


def format_rules_table(rules: list[dict], title: str):
    """Format rules as a table with interface, condition and comment columns."""
    if not rules:
        print(f"  (no {title.lower()} found)")
        return

    print(
        f"{'Num':<3} {'Target':<12} {'Prot':<4} {'Interface':<15} {'Condition':<25} {'Comment':<30}"
    )
    print("-" * 95)

    for rule in rules:
        num = rule.get("num", "")
        target = rule.get("target", "")[:11]  # truncate if too long
        prot = rule.get("prot", "")
        interface = rule.get("interface", "")[:14]  # truncate if too long
        condition = rule.get("condition", "")[:24]  # truncate if too long
        comment = rule.get("comment", "")[:29]  # truncate if too long

        print(f"{num:<3} {target:<12} {prot:<4} {interface:<15} {condition:<25} {comment:<30}")


def show_rules_family(ipt: str, label: str):
    print(f"\n=== {label} Rules ===")

    # Check HTTP chain
    if chain_exists(ipt, "nat", USER_CHAIN_HTTP):
        print(f"\n[+] HTTP chain '{USER_CHAIN_HTTP}' contents:")
        res = run([ipt, "-t", "nat", "-nL", USER_CHAIN_HTTP, "--line-numbers"])
        if res.returncode == 0 and res.stdout.strip():
            lines = res.stdout.splitlines()
            rule_lines = [line for line in lines[2:] if line.strip()]
            if rule_lines:
                rules = [parse_iptables_rule(line) for line in rule_lines]
                format_rules_table(rules, "HTTP rules")
            else:
                print("  (empty)")
        else:
            print("  (empty or error)")
    else:
        print(f"\n[-] HTTP chain '{USER_CHAIN_HTTP}' does not exist")

    # Check TCP chain
    if chain_exists(ipt, "nat", USER_CHAIN_TCP):
        print(f"\n[+] TCP chain '{USER_CHAIN_TCP}' contents:")
        res = run([ipt, "-t", "nat", "-nL", USER_CHAIN_TCP, "--line-numbers"])
        if res.returncode == 0 and res.stdout.strip():
            lines = res.stdout.splitlines()
            rule_lines = [line for line in lines[2:] if line.strip()]
            if rule_lines:
                rules = [parse_iptables_rule(line) for line in rule_lines]
                format_rules_table(rules, "TCP rules")
            else:
                print("  (empty)")
        else:
            print("  (empty or error)")
    else:
        print(f"\n[-] TCP chain '{USER_CHAIN_TCP}' does not exist")

    # Show PREROUTING rules that jump to our chains
    print("\n[+] PREROUTING rules (jumping to proxy chains):")
    res = run([ipt, "-t", "nat", "-nL", "PREROUTING", "--line-numbers"])
    if res.returncode == 0:
        lines = res.stdout.splitlines()
        envoy_rules = []
        for line in lines[2:]:
            if USER_CHAIN_HTTP in line or USER_CHAIN_TCP in line or "envoy:" in line:
                envoy_rules.append(parse_iptables_rule(line))
        format_rules_table(envoy_rules, "envoy-related rules")
    else:
        print("  (error reading PREROUTING rules)")

    # Show OUTPUT rules for local traffic
    print("\n[+] OUTPUT rules (local traffic to Envoy):")
    res = run([ipt, "-t", "nat", "-nL", "OUTPUT", "--line-numbers"])
    if res.returncode == 0:
        lines = res.stdout.splitlines()
        envoy_rules = []
        for line in lines[2:]:
            if f"uid !{ENVOY_UID}" in line or "envoy:" in line:
                envoy_rules.append(parse_iptables_rule(line))
        format_rules_table(envoy_rules, "envoy-related rules")
    else:
        print("  (error reading OUTPUT rules)")

    # Show protection rules in raw table if enabled
    if PROTECT_ENVOY_PORT:
        print("\n[+] Protection rules (raw table, blocking direct access):")
        res = run([ipt, "-t", "raw", "-nL", "PREROUTING", "--line-numbers"])
        if res.returncode == 0:
            lines = res.stdout.splitlines()
            protection_rules = []
            for line in lines[2:]:
                if (
                    f"dpt:{ENVOY_HTTP_PORT}" in line
                    or f"dpt:{ENVOY_TCP_PORT}" in line
                    or "envoy:" in line
                ):
                    protection_rules.append(parse_iptables_rule(line))
            format_rules_table(protection_rules, "protection rules")
        else:
            print("  (error reading raw PREROUTING rules)")


def info():
    # Resolve bridges for display
    if BRIDGE_IFS.strip().lower() in {"auto", ""}:
        excl_ifs = detect_bridges()
    else:
        excl_ifs = [x for x in BRIDGE_IFS.split() if x]

    http_ports, tcp_ports = load_ports()

    print("=== CTF Proxy iptables Configuration Info ===")
    print(f"Envoy HTTP Port: {ENVOY_HTTP_PORT}")
    print(f"Envoy TCP Port: {ENVOY_TCP_PORT}")
    print(f"Envoy UID: {ENVOY_UID}")
    print(f"HTTP Chain: {USER_CHAIN_HTTP}")
    print(f"TCP Chain: {USER_CHAIN_TCP}")
    print(f"Configured HTTP Ports: {', '.join(map(str, http_ports)) if http_ports else '<none>'}")
    print(f"Configured TCP Ports: {', '.join(map(str, tcp_ports)) if tcp_ports else '<none>'}")
    print(f"Excluded Bridge Interfaces: {', '.join(excl_ifs) if excl_ifs else '<none>'}")
    print(f"Protect Envoy Ports: {'Yes' if PROTECT_ENVOY_PORT else 'No'}")
    print(f"IPv6 Enabled: {'Yes' if ipv6_wanted() else 'No'}")

    show_rules_family(IPT, "IPv4")
    if ipv6_wanted():
        show_rules_family(IP6T, "IPv6")


def usage():
    exe = Path(sys.argv[0]).name
    print(
        f"""Usage: sudo {exe} setup|teardown|add-port <port>|remove-port <port>|info

Environment overrides:
  PORTS_FILE={PORTS_FILE or "<unset>"}   # path to config file listing ports (YAML)
  ENVOY_HTTP_PORT={ENVOY_HTTP_PORT}      # HTTP proxy port
  ENVOY_TCP_PORT={ENVOY_TCP_PORT}       # TCP proxy port
  ENVOY_UID={ENVOY_UID}
  BRIDGE_IFS={BRIDGE_IFS}        # space-separated list or "auto"
  PROTECT_ENVOY_PORT={"1" if PROTECT_ENVOY_PORT else "0"}
  ENABLE_IPV6={ENABLE_IPV6}      # auto|1|0
  IPT={IPT}
  IP6T={IP6T}
  USER_CHAIN_HTTP={USER_CHAIN_HTTP}
  USER_CHAIN_TCP={USER_CHAIN_TCP}

Notes:
  • setup: Configure redirects for all ports from PORTS_FILE.
  • teardown: Remove all existing redirects.
  • add-port <port>: Add redirect for a specific port.
  • remove-port <port>: Remove redirect for a specific port.
  • info: Display current iptables rules related to proxying.
  • Services are classified by type in PORTS_FILE:
    - HTTP/WS services (type: http, https, ws, wss) → :{ENVOY_HTTP_PORT}
    - TCP services (type: tcp, udp, etc.) → :{ENVOY_TCP_PORT}
    - YAML example:
        services:
          - name: web
            port: 8080
            type: http
          - name: database
            port: 3306
            type: tcp
  • IPv4 and IPv6 traffic is redirected based on service type.
  • Local traffic (127.0.0.1 and ::1) is redirected too; Envoy's UID is excluded to avoid loops.
  • Direct remote hits to proxy ports are dropped when PROTECT_ENVOY_PORT=1.
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
    elif cmd == "info":
        info()
    elif cmd == "add-port":
        if len(sys.argv) < 3:
            print("Error: add-port command requires a port number", file=sys.stderr)
            usage()
        try:
            port = int(sys.argv[2])
            if not (1 <= port <= 65535):
                raise ValueError("Port must be between 1 and 65535")
            add_port(port)
        except ValueError as e:
            print(f"Error: Invalid port number - {e}", file=sys.stderr)
            sys.exit(1)
    elif cmd == "remove-port":
        if len(sys.argv) < 3:
            print("Error: remove-port command requires a port number", file=sys.stderr)
            usage()
        try:
            port = int(sys.argv[2])
            if not (1 <= port <= 65535):
                raise ValueError("Port must be between 1 and 65535")
            remove_port(port)
        except ValueError as e:
            print(f"Error: Invalid port number - {e}", file=sys.stderr)
            sys.exit(1)
    else:
        usage()


if __name__ == "__main__":
    main()
