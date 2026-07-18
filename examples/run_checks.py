import argparse
import itertools
import os
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path

CHECKS_DIR_NAME = "ctf-proxy-checks"
ATTACKS_DIR_NAME = "ctf-proxy-attacks"
REPO_ROOT = Path(__file__).resolve().parents[1]
GAMESERVER_SRC = REPO_ROOT / "3rd" / "ctf-gameserver" / "src"


@dataclass
class Check:
    name: str
    service: str
    path: Path
    kind: str = "check"


@dataclass
class Result:
    service: str
    name: str
    tick: int
    returncode: int
    duration: float
    output: str
    timed_out: bool

    @property
    def ok(self) -> bool:
        return self.returncode == 0 and not self.timed_out

    @property
    def status(self) -> str:
        if self.timed_out:
            return "TIMEOUT"
        return "OK" if self.returncode == 0 else f"FAIL({self.returncode})"


@dataclass
class Stat:
    service: str
    name: str
    kind: str = "check"
    runs: int = 0
    ok: int = 0
    fail: int = 0
    timeout: int = 0
    total_duration: float = 0.0
    last: str = ""
    last_fail_tail: str = ""


def discover_checks(root: Path) -> list[Check]:
    checks: list[Check] = []
    for kind, dir_name in (("check", CHECKS_DIR_NAME), ("attack", ATTACKS_DIR_NAME)):
        for base_dir in sorted(root.rglob(dir_name)):
            if not base_dir.is_dir():
                continue
            for path in sorted(base_dir.glob("*.py")):
                if path.name.startswith((".", "_")):
                    continue
                checks.append(Check(name=path.stem, service=base_dir.parent.name, path=path, kind=kind))
    return checks


def run_check(check: Check, host: str, team: str, tick: int, timeout: float) -> Result:
    env = dict(os.environ)
    existing = env.get("PYTHONPATH")
    env["PYTHONPATH"] = str(GAMESERVER_SRC) + (os.pathsep + existing if existing else "")
    env["CHECK_HOST"] = host
    env["CHECK_TEAM"] = team
    env["CHECK_TICK"] = str(tick)

    start = time.monotonic()
    try:
        proc = subprocess.run(
            [sys.executable, str(check.path), host, team, str(tick)],
            cwd=check.path.parent,
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return Result(
            service=check.service,
            name=check.name,
            tick=tick,
            returncode=proc.returncode,
            duration=time.monotonic() - start,
            output=(proc.stdout + proc.stderr)[-2000:],
            timed_out=False,
        )
    except subprocess.TimeoutExpired as exc:
        output = exc.output or ""
        if isinstance(output, bytes):
            output = output.decode(errors="ignore")
        return Result(
            service=check.service,
            name=check.name,
            tick=tick,
            returncode=-1,
            duration=time.monotonic() - start,
            output=output[-2000:],
            timed_out=True,
        )


def run_check_limited(
    check: Check, host: str, team: str, tick: int, timeout: float, limiter: threading.Semaphore | None
) -> Result:
    if limiter is not None:
        limiter.acquire()
    try:
        return run_check(check, host, team, tick, timeout)
    finally:
        if limiter is not None:
            limiter.release()


def run_batch(
    check: Check,
    host: str,
    team: str,
    ticks: "itertools.count[int]",
    timeout: float,
    limiter: threading.Semaphore | None,
    count: int,
) -> list[Result]:
    """Run the check `count` times in parallel (extra load), returning all results."""
    if count <= 1:
        return [run_check_limited(check, host, team, next(ticks), timeout, limiter)]

    assigned = [next(ticks) for _ in range(count)]
    results: list[Result] = []
    rlock = threading.Lock()

    def worker(tk: int) -> None:
        result = run_check_limited(check, host, team, tk, timeout, limiter)
        with rlock:
            results.append(result)

    threads = [threading.Thread(target=worker, args=(tk,), daemon=True) for tk in assigned]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    return results


def last_line(text: str) -> str:
    for line in reversed(text.strip().splitlines()):
        if line.strip():
            return line.strip()
    return ""


def check_loop(
    check: Check,
    host: str,
    team: str,
    timeout: float,
    interval: float,
    once: bool,
    start_tick: int,
    stat: Stat,
    lock: threading.Lock,
    stop: threading.Event,
    limiter: threading.Semaphore | None,
    extra_load: int = 1,
) -> None:
    ticks = itertools.count(start_tick)
    while not stop.is_set():
        results = run_batch(check, host, team, ticks, timeout, limiter, extra_load)

        with lock:
            for result in results:
                stat.runs += 1
                stat.total_duration += result.duration
                if result.timed_out:
                    stat.timeout += 1
                    stat.last = "TIMEOUT"
                    stat.last_fail_tail = last_line(result.output)
                elif result.returncode == 0:
                    stat.ok += 1
                    stat.last = "OK"
                else:
                    stat.fail += 1
                    stat.last = result.status
                    stat.last_fail_tail = last_line(result.output)

        if once:
            break
        stop.wait(interval)


def snapshot(
    stats: dict[tuple[str, str, str], Stat], lock: threading.Lock
) -> tuple[list[tuple], int, int]:
    with lock:
        rows = sorted(stats.values(), key=lambda s: (s.kind, s.service, s.name))
        total_runs = sum(s.runs for s in rows)
        total_ok = sum(s.ok for s in rows)
        data = [
            (
                s.kind,
                s.service,
                s.name,
                s.runs,
                s.ok,
                s.fail,
                s.timeout,
                s.total_duration / s.runs if s.runs else 0.0,
                s.last,
                s.last_fail_tail,
            )
            for s in rows
        ]
    return data, total_runs, total_ok


def print_report(stats: dict[tuple[str, str, str], Stat], lock: threading.Lock, elapsed: float) -> None:
    data, total_runs, total_ok = snapshot(stats, lock)
    rate = total_runs / elapsed if elapsed else 0.0
    print(f"\n=== {elapsed:.0f}s | {total_runs} runs, {total_ok} OK, {rate:.1f} runs/s ===", flush=True)
    for kind, service, name, runs, ok, fail, timeout, avg, last, tail in data:
        loop_rate = runs / elapsed if elapsed else 0.0
        tag = "atk" if kind == "attack" else "chk"
        print(
            f"  [{tag}] {service}/{name:<8} runs={runs:<4} ok={ok:<4} fail={fail:<3} to={timeout:<2} "
            f"avg={avg:.1f}s {loop_rate:.2f}/s [{last}]",
            flush=True,
        )
        if last != "OK" and tail:
            print(f"      {tail}", flush=True)


def build_table(stats: dict[tuple[str, str, str], Stat], lock: threading.Lock, elapsed: float):
    from rich.table import Table

    data, total_runs, total_ok = snapshot(stats, lock)
    rate = total_runs / elapsed if elapsed else 0.0
    table = Table(
        title=f"{elapsed:.0f}s  |  {total_runs} runs  |  {total_ok} OK  |  {rate:.1f} runs/s",
        title_style="bold",
        expand=True,
    )
    table.add_column("kind", no_wrap=True)
    table.add_column("service", no_wrap=True)
    table.add_column("runs", justify="right")
    table.add_column("ok", justify="right")
    table.add_column("fail", justify="right")
    table.add_column("to", justify="right")
    table.add_column("avg", justify="right")
    table.add_column("rate", justify="right")
    table.add_column("last", no_wrap=True, max_width=48, overflow="ellipsis")

    colors = {"OK": "green", "TIMEOUT": "yellow", "": "dim"}
    for kind, service, name, runs, ok, fail, timeout, avg, last, tail in data:
        loop_rate = runs / elapsed if elapsed else 0.0
        color = colors.get(last, "red")
        status = last if last == "OK" else (f"{last}  {tail}" if tail else last)
        table.add_row(
            "[magenta]atk[/magenta]" if kind == "attack" else "chk",
            f"{service}/{name}",
            str(runs),
            str(ok),
            str(fail) if fail else "-",
            str(timeout) if timeout else "-",
            f"{avg:.1f}s",
            f"{loop_rate:.2f}/s",
            f"[{color}]{status}[/{color}]",
        )
    return table


def run_live(
    stats: dict[tuple[str, str, str], Stat],
    lock: threading.Lock,
    threads: list[threading.Thread],
    stop: threading.Event,
    refresh: float,
    start: float,
) -> None:
    from rich.live import Live

    with Live(build_table(stats, lock, 0.0), refresh_per_second=4, screen=False) as live:
        while any(thread.is_alive() for thread in threads):
            stop.wait(refresh)
            live.update(build_table(stats, lock, time.monotonic() - start))
        live.update(build_table(stats, lock, time.monotonic() - start))


def interactive_supported(force_plain: bool) -> bool:
    return not force_plain and sys.stdout.isatty()


def parse_extra_load(value: str) -> int:
    text = value.strip().lower()
    if text.endswith("x"):
        text = text[:-1]
    try:
        n = int(text)
    except ValueError:
        raise argparse.ArgumentTypeError(f"invalid --extra-load value: {value!r} (use e.g. 2 or 2x)")
    if n < 1:
        raise argparse.ArgumentTypeError("--extra-load must be >= 1")
    return n


def main() -> None:
    parser = argparse.ArgumentParser(description="Run each ctf-proxy-check on its own independent loop.")
    parser.add_argument("--host", required=True, help="Target host/IP passed to every check.")
    parser.add_argument("--team", default="1")
    parser.add_argument("--tick", type=int, default=0, help="Starting tick (incremented per run, globally).")
    parser.add_argument("--interval", type=float, default=5.0, help="Seconds a check loop waits between its own runs.")
    parser.add_argument(
        "--attack-interval", type=float, default=60.0, help="Seconds an attack loop waits between its own runs."
    )
    parser.add_argument("--no-attacks", action="store_true", help="Discover/run checks only, skip attacks.")
    parser.add_argument("--timeout", type=float, default=120.0, help="Per-run timeout in seconds.")
    parser.add_argument("--repeat", type=int, default=1, help="Concurrent loops per check (load amplification).")
    parser.add_argument(
        "--extra-load",
        type=parse_extra_load,
        default=1,
        metavar="Nx",
        help="Run each check N times in parallel per iteration to amplify load (e.g. 2x or 2).",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=0,
        help="Optional global cap on concurrent checks (0 = unbounded). A cap re-couples fast/slow checks.",
    )
    parser.add_argument("--report-every", type=float, default=10.0, help="Seconds between aggregate reports.")
    parser.add_argument("--once", action="store_true", help="Run each check once (x --repeat) and exit.")
    parser.add_argument(
        "--plain", action="store_true", help="Force plain text output (disable the interactive TUI)."
    )
    parser.add_argument("--filter", default="", help="Only run checks whose service or name contains this.")
    parser.add_argument("root", nargs="?", default=str(Path(__file__).resolve().parent))
    args = parser.parse_args()

    root = Path(args.root).resolve()
    checks = discover_checks(root)
    if args.no_attacks:
        checks = [c for c in checks if c.kind == "check"]
    if args.filter:
        checks = [c for c in checks if args.filter in c.service or args.filter in c.name]
    if not checks:
        print(f"No checks found under {root}/**/{{{CHECKS_DIR_NAME},{ATTACKS_DIR_NAME}}}/*.py")
        sys.exit(1)

    repeat = max(1, args.repeat)
    n_checks = sum(1 for c in checks if c.kind == "check")
    n_attacks = sum(1 for c in checks if c.kind == "attack")
    services = sorted({c.service for c in checks})
    print(f"Discovered {n_checks} checks + {n_attacks} attacks across {len(services)} services: {', '.join(services)}")
    cap = f"{args.workers}" if args.workers > 0 else "unbounded"
    print(
        f"loops={len(checks) * repeat} ({repeat}/entry) extra-load={args.extra_load}x "
        f"check-interval={args.interval}s attack-interval={args.attack_interval}s "
        f"timeout={args.timeout}s cap={cap}"
    )

    stats: dict[tuple[str, str, str], Stat] = {
        (c.kind, c.service, c.name): Stat(service=c.service, name=c.name, kind=c.kind) for c in checks
    }
    lock = threading.Lock()
    stop = threading.Event()
    limiter = threading.Semaphore(args.workers) if args.workers > 0 else None

    threads = [
        threading.Thread(
            target=check_loop,
            args=(
                check,
                args.host,
                args.team,
                args.timeout,
                args.attack_interval if check.kind == "attack" else args.interval,
                args.once,
                args.tick,
                stats[(check.kind, check.service, check.name)],
                lock,
                stop,
                limiter,
                args.extra_load,
            ),
            daemon=True,
        )
        for check in checks
        for _ in range(repeat)
    ]

    interactive = interactive_supported(args.plain) and not args.once

    start = time.monotonic()
    for thread in threads:
        thread.start()

    try:
        if args.once:
            for thread in threads:
                thread.join()
        elif interactive:
            run_live(stats, lock, threads, stop, 0.5, start)
        else:
            while any(thread.is_alive() for thread in threads):
                stop.wait(args.report_every)
                print_report(stats, lock, time.monotonic() - start)
    except KeyboardInterrupt:
        print("\nStopping...", flush=True)
    finally:
        stop.set()
        for thread in threads:
            thread.join(timeout=args.timeout + 5)

    print_report(stats, lock, time.monotonic() - start)


if __name__ == "__main__":
    main()
