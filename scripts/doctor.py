#!/usr/bin/env python3
"""Preflight diagnostics for building the Chromium Android fork.

Never downloads/installs tools or changes source.
Usage:
  python3 scripts/doctor.py --stage checkout --root ~/chromium
  python3 scripts/doctor.py --stage build --root ~/chromium
"""
import argparse
import platform
import shutil
import subprocess
import sys
from pathlib import Path


def check_disk(path: Path) -> int:
    existing = path.resolve()
    while not existing.exists():
        if existing.parent == existing:
            break
        existing = existing.parent
    available = shutil.disk_usage(existing).free // (1024 ** 3)
    if available < 100:
        print(f"WARN  Disk: {available} GiB free (Chromium Android recommends 100 GB+).")
    else:
        print(f"OK    Disk: {available} GiB free.")
    return available


def read_mem_gib() -> float | None:
    try:
        for line in Path("/proc/meminfo").read_text().splitlines():
            if line.startswith("MemTotal:"):
                return int(line.split()[1]) / 1024 / 1024
    except OSError:
        pass
    return None


def git_head(src: Path) -> str | None:
    try:
        return subprocess.check_output(
            ["git", "-C", str(src), "rev-parse", "HEAD"],
            text=True, stderr=subprocess.DEVNULL,
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def run() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", choices=("checkout", "build"), default="checkout")
    parser.add_argument("--root", type=Path, default=Path.home() / "chromium")
    args = parser.parse_args()
    errors = []

    if platform.system() != "Linux" or platform.machine() != "x86_64":
        errors.append("Official Chromium Android build host must be Linux x86-64.")
    else:
        print("OK    Build host: Linux x86-64")

    check_disk(args.root)
    mem = read_mem_gib()
    if mem is not None:
        print(f"{'WARN' if mem < 16 else 'OK  '}  RAM: {mem:.1f} GiB "
              "(16 GiB+ recommended)")
    for tool in ("git", "python3"):
        if shutil.which(tool):
            print(f"OK    Tool: {tool}")
        else:
            errors.append(f"Missing mandatory tool: {tool}")

    if args.stage == "build":
        src = args.root / "src"
        pin_file = Path(__file__).resolve().parent.parent / "UPSTREAM_REVISION"
        try:
            pin = pin_file.read_text().strip()
        except OSError:
            pin = None
        if not pin:
            errors.append("Missing UPSTREAM_REVISION.")
        actual = git_head(src)
        if actual is None:
            errors.append(f"No git checkout in {src}.")
        elif actual != pin:
            errors.append(
                f"Unexpected Chromium revision {actual}; expected {pin}. "
                "Run scripts/bootstrap.sh against a clean checkout."
            )
        else:
            print(f"OK    Pinned Chromium SHA: {actual}")

        # GN and ninja may be supplied by depot_tools in PATH.
        for tool in ("gn", "autoninja"):
            if shutil.which(tool):
                print(f"OK    Tool: {tool}")
            else:
                errors.append(f"Missing build tool in PATH: {tool}")

    for error in errors:
        print(f"ERROR {error}", file=sys.stderr)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(run())
