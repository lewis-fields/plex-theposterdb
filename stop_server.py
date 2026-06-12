#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import platform
import re
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request


DEFAULT_PORT = int(os.environ.get("PORT", "8765"))


def run(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, capture_output=True, text=True, check=False)


def listening_pids_windows(port: int) -> set[int]:
    result = run(["netstat", "-ano", "-p", "tcp"])
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "netstat failed")

    pids: set[int] = set()
    pattern = re.compile(rf"^\s*TCP\s+\S+:{port}\s+\S+\s+LISTENING\s+(\d+)\s*$", re.I)
    for line in result.stdout.splitlines():
        match = pattern.match(line)
        if match:
            pids.add(int(match.group(1)))
    return pids


def listening_pids_unix(port: int) -> set[int]:
    result = run(["lsof", "-ti", f"tcp:{port}"])
    if result.returncode == 0:
        return {int(line) for line in result.stdout.splitlines() if line.strip().isdigit()}
    return set()


def server_command_pids_unix() -> set[int]:
    result = run(["pgrep", "-f", r"python3? .*server\.py|python .*server\.py"])
    if result.returncode != 0:
        return set()
    current_pid = os.getpid()
    return {int(line) for line in result.stdout.splitlines() if line.strip().isdigit() and int(line) != current_pid}


def process_exists(pid: int) -> bool:
    if platform.system() == "Windows":
        result = run(["tasklist", "/FI", f"PID eq {pid}", "/NH"])
        return result.returncode == 0 and str(pid) in result.stdout
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def request_shutdown(port: int) -> bool:
    request = urllib.request.Request(
        f"http://127.0.0.1:{port}/api/shutdown",
        headers={"X-TPDB-Stop": "1"},
        method="POST",
        data=b"{}",
    )
    try:
        with urllib.request.urlopen(request, timeout=2):
            return True
    except (OSError, urllib.error.URLError, TimeoutError):
        return False


def wait_until_stopped(pids: set[int], timeout: float = 5.0) -> set[int]:
    deadline = time.monotonic() + timeout
    remaining = set(pids)
    while remaining and time.monotonic() < deadline:
        remaining = {pid for pid in remaining if process_exists(pid)}
        if remaining:
            time.sleep(0.2)
    return {pid for pid in remaining if process_exists(pid)}


def stop_windows(pids: set[int]) -> None:
    for pid in sorted(pids):
        try:
            os.kill(pid, signal.SIGTERM)
            continue
        except OSError:
            pass

        result = run(["taskkill", "/PID", str(pid), "/T", "/F"])
        if result.returncode != 0:
            message = (result.stderr or result.stdout).strip()
            raise RuntimeError(f"Could not stop PID {pid}: {message}")


def stop_unix(pids: set[int]) -> None:
    for pid in sorted(pids):
        os.kill(pid, signal.SIGTERM)
    remaining = wait_until_stopped(pids)
    for pid in sorted(remaining):
        os.kill(pid, signal.SIGKILL)


def find_pids(port: int) -> set[int]:
    if platform.system() == "Windows":
        return listening_pids_windows(port)
    pids = listening_pids_unix(port)
    return pids or server_command_pids_unix()


def main() -> int:
    parser = argparse.ArgumentParser(description="Stop the local TPDb Plex Poster Picker server.")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help=f"Port to stop, defaults to {DEFAULT_PORT}.")
    args = parser.parse_args()

    try:
        pids = find_pids(args.port)
        if not pids:
            print(f"TPDb Plex Poster Picker is not running on port {args.port}.")
            return 0

        print(f"Stopping TPDb Plex Poster Picker on port {args.port}: {', '.join(str(pid) for pid in sorted(pids))}")
        if request_shutdown(args.port):
            print("Shutdown request accepted.")
        elif platform.system() == "Windows":
            stop_windows(pids)
        else:
            stop_unix(pids)

        remaining = wait_until_stopped(pids)
        if remaining:
            print(f"Could not stop PID(s): {', '.join(str(pid) for pid in sorted(remaining))}", file=sys.stderr)
            return 1

        print("Server stopped.")
        return 0
    except Exception as exc:
        print(f"Failed to stop server: {exc}", file=sys.stderr)
        if platform.system() == "Windows":
            print("If this process was started as administrator, run this stop command from an elevated terminal.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
