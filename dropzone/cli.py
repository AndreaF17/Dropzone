"""Command-line entry point for dropzone.

Usage examples::

    dz                                  # 0.0.0.0:8000, ./uploads
    dz -H 127.0.0.1 -p 9001 -d /data    # custom bind + dir
    dz -t                               # require a generated bearer token (printed at startup)
    dz --token s3cret                   # require a specific bearer token
    python -m dropzone --help
"""

from __future__ import annotations

import argparse
import logging
import os
import secrets
import sys
from pathlib import Path

from . import __version__

GENERATE = object()  # sentinel: -t given without a value

BANNER_LINES = r"""
  ___  ___  ___  ___ _______ _  _ ___
 |   \| _ \/ _ \| _ \_  / _ \| \| | __|
 | |) |   / (_) |  _// / (_) | .` | _|
 |___/|_|_\\___/|_| /___\___/|_|\_|___|
""".strip("\n").splitlines()

# ANSI SGR codes. Kept dependency-free; disabled when not a TTY or NO_COLOR is set.
RESET, BOLD, DIM = "0", "1", "2"
RED, GREEN, YELLOW, MAGENTA, CYAN = "31", "32", "33", "35", "36"
BRIGHT_MAGENTA, BRIGHT_CYAN = "95", "96"
_color = False


def use_color(no_color_flag: bool = False) -> bool:
    """Honor --no-color, NO_COLOR and FORCE_COLOR; otherwise color only on a TTY."""
    if no_color_flag or os.environ.get("NO_COLOR"):
        return False
    if os.environ.get("FORCE_COLOR"):
        return True
    return sys.stdout.isatty() and os.environ.get("TERM") != "dumb"


def paint(text: str, *codes: str) -> str:
    if not _color or not codes:
        return text
    return f"\033[{';'.join(codes)}m{text}\033[0m"


def banner() -> str:
    # Magenta -> cyan gradient, one color per line.
    colors = [BRIGHT_MAGENTA, MAGENTA, CYAN, BRIGHT_CYAN]
    lines = [paint(line, BOLD, c) for line, c in zip(BANNER_LINES, colors)]
    lines[-1] += "  " + paint(f"v{__version__}", DIM)
    return "\n" + "\n".join(lines) + "\n"


def status(label: str, value: str, *codes: str) -> str:
    return f"  {paint('[*]', BOLD, CYAN)} {paint(f'{label:<9}', DIM)} : {paint(value, *(codes or (BOLD,)))}"


class ColorFormatter(logging.Formatter):
    """Colors the timestamp, level and logger name of console log records."""

    LEVELS = {logging.DEBUG: DIM, logging.INFO: GREEN, logging.WARNING: YELLOW,
              logging.ERROR: RED, logging.CRITICAL: RED}

    def format(self, record: logging.LogRecord) -> str:
        ts = paint(self.formatTime(record, "%H:%M:%S"), DIM)
        levelname = {"WARNING": "WARN", "CRITICAL": "CRIT"}.get(record.levelname, record.levelname)
        level = paint(f"{levelname:<5}", BOLD, self.LEVELS.get(record.levelno, RESET))
        name = paint(record.name, MAGENTA)
        msg = record.getMessage()
        if record.exc_info:
            msg += "\n" + self.formatException(record.exc_info)
        return f"{ts} {level} {name}: {msg}"


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="dz",
        description="A FastAPI file-upload server for a lab. Serves a browser "
        "upload page and receives files over HTTP (curl / PowerShell / wget), "
        "sorting them into <upload-dir>/<client-ip>/. Received-file events are "
        "printed to this console only.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Use only against systems you are authorized to test.",
    )
    p.add_argument("-H", "--host", default=os.environ.get("HOST", "0.0.0.0"),
                   help="interface to bind (default: 0.0.0.0)")
    p.add_argument("-p", "--port", type=int, default=int(os.environ.get("PORT", "8000")),
                   help="port to listen on (default: 8000)")
    p.add_argument("-d", "--dir", default=os.environ.get("UPLOAD_DIR", "uploads"),
                   help="directory to store uploads (default: ./uploads)")
    p.add_argument("-t", "--token", nargs="?", const=GENERATE, default=os.environ.get("AUTH_TOKEN"),
                   help="require a bearer token on every upload; with no value a random "
                   "one is generated and printed at startup (default: none)")
    p.add_argument("--trust-proxy", action="store_true",
                   default=os.environ.get("TRUST_PROXY", "").lower() in {"1", "true", "yes"},
                   help="trust X-Forwarded-For for the client IP (only behind a reverse proxy)")
    p.add_argument("--reload", action="store_true", help="auto-reload on code changes (development)")
    p.add_argument("--no-color", action="store_true", help="disable colored output (also: NO_COLOR=1)")
    p.add_argument("-v", "--verbose", action="store_true",
                   help="also show uvicorn startup and per-request access logs "
                   "(default: only received files, rejected uploads and errors)")
    p.add_argument("-V", "--version", action="version", version=f"dropzone {__version__}")
    return p


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)

    # Push settings into the environment the app reads.
    os.environ["UPLOAD_DIR"] = str(Path(args.dir).resolve())
    if args.token is GENERATE:
        args.token = secrets.token_urlsafe(18)
    if args.token:
        os.environ["AUTH_TOKEN"] = args.token
    os.environ["TRUST_PROXY"] = "1" if args.trust_proxy else ""

    global _color
    _color = use_color(args.no_color)
    if _color and os.name == "nt":
        os.system("")  # enables ANSI escape processing in the legacy Windows console

    handler = logging.StreamHandler()
    handler.setFormatter(ColorFormatter())
    logging.basicConfig(level=logging.INFO, handlers=[handler])

    upload_dir = os.environ["UPLOAD_DIR"]
    print(banner())
    print(status("listening", f"http://{args.host}:{args.port}", BOLD, BRIGHT_CYAN))
    print(status("storing", f"{upload_dir}/<client-ip>/"))
    if args.token:
        print(status("auth", "bearer token required", BOLD, GREEN))
        print(status("token", args.token, BOLD, BRIGHT_MAGENTA))
    else:
        print(status("auth", "open (no token)", BOLD, YELLOW))
    if args.trust_proxy:
        print(status("proxy", "trusting X-Forwarded-For", BOLD, YELLOW))
    else:
        print(status("proxy", "direct peer IP"))
    print(f"  {paint('[*]', BOLD, CYAN)} {paint('received files are logged below; Ctrl-C to stop', DIM)}\n")
    sys.stdout.flush()  # keep the banner ahead of uvicorn's (stderr) startup lines

    import uvicorn

    # By default only our own events (received / rejected uploads) and real
    # errors reach the console; uvicorn's startup chatter and access log don't.
    log_level = "info" if args.verbose else "warning"
    uvicorn.run("dropzone.server:app", host=args.host, port=args.port,
                reload=args.reload, log_level=log_level, access_log=args.verbose,
                use_colors=_color)


if __name__ == "__main__":
    main()
