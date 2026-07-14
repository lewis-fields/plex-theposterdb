#!/usr/bin/env python3
from __future__ import annotations

import os
from pathlib import Path


def numeric_id(name: str, default: int) -> int:
    value = os.environ.get(name, str(default))
    try:
        identifier = int(value)
    except ValueError as exc:
        raise SystemExit(f"{name} must be a numeric ID, got {value!r}.") from exc
    if identifier < 0:
        raise SystemExit(f"{name} must not be negative.")
    return identifier


def main() -> None:
    command = os.sys.argv[1:] or ["python", "server.py"]
    puid = numeric_id("PUID", 10001)
    pgid = numeric_id("PGID", 10001)

    if os.geteuid() == 0:
        config_path = Path(os.environ.get("CONFIG_PATH", "/config/config.json"))
        config_path.parent.mkdir(parents=True, exist_ok=True)
        os.chown(config_path.parent, puid, pgid)
        if config_path.exists():
            os.chown(config_path, puid, pgid)

        os.setgroups([])
        os.setgid(pgid)
        os.setuid(puid)

    os.execvp(command[0], command)


if __name__ == "__main__":
    main()
