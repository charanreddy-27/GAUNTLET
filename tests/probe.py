#!/usr/bin/env python3
"""A tiny, dependency-free stand-in for `true`, `false`, `sleep` and friends.

The scheduler tests need shell commands with precise exit codes and timing.
Coreutils gives you those on Linux and macOS and nothing at all on Windows,
so the tests would quietly become "works on my OS". This script is the
portable substitute: same behaviours, one Python interpreter, everywhere.

Usage (see tests/conftest.py for the helper that builds these):
    probe.py ok                 exit 0
    probe.py fail               exit 1
    probe.py sleep <seconds>    sleep, then exit 0
    probe.py touch <path>       create an empty file, exit 0
    probe.py exists <path>      exit 0 if the path exists, else 1
    probe.py fail-once <path>   first call creates <path> and exits 1;
                                every later call exits 0
    probe.py echo <words...>    print the words, exit 0
"""
import sys
import time
from pathlib import Path

_THIS = Path(__file__).resolve()


def cmd(*args) -> str:
    """Build a shell command line that runs this script with `args`.

    Double-quoting the interpreter and script path keeps it valid under both
    POSIX shells and cmd.exe, so one command string works on every OS.
    """
    parts = [sys.executable, str(_THIS), *[str(a) for a in args]]
    return " ".join(f'"{p}"' for p in parts)


def main(argv: list[str]) -> int:
    if not argv:
        print("probe: no command", file=sys.stderr)
        return 2
    command, args = argv[0], argv[1:]

    if command == "ok":
        return 0
    if command == "fail":
        return 1
    if command == "sleep":
        time.sleep(float(args[0]))
        return 0
    if command == "touch":
        Path(args[0]).touch()
        return 0
    if command == "exists":
        return 0 if Path(args[0]).exists() else 1
    if command == "fail-once":
        marker = Path(args[0])
        if marker.exists():
            return 0
        marker.touch()
        return 1
    if command == "echo":
        print(" ".join(args))
        return 0

    print(f"probe: unknown command {command!r}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
