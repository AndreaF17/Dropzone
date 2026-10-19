"""FastAPI application: a file-upload server for a lab.

Accepts files via multipart/form-data (browser form, ``curl -F``) and via raw
request body (``curl --data-binary``, PowerShell ``-InFile``), storing each one
under ``<UPLOAD_DIR>/<client-ip>/``.

Received-file events are written to the ``dropzone`` logger, i.e. the server's
console — they are never exposed through the web UI or any HTTP endpoint.
"""

from __future__ import annotations

import ipaddress
import logging
import os
import re
import uuid
from pathlib import Path

from fastapi import FastAPI, File, Header, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse

log = logging.getLogger("dropzone")

STATIC_DIR = Path(__file__).parent / "static"
INDEX_HTML = STATIC_DIR / "index.html"


def _env_upload_dir() -> Path:
    return Path(os.environ.get("UPLOAD_DIR", "uploads")).resolve()


def _trust_proxy() -> bool:
    return os.environ.get("TRUST_PROXY", "").lower() in {"1", "true", "yes"}


def _auth_token() -> str | None:
    return os.environ.get("AUTH_TOKEN") or None


def check_auth(authorization: str | None, x_token: str | None, ip: str) -> None:
    token = _auth_token()
    if not token:
        return
    supplied = x_token
    if authorization and authorization.lower().startswith("bearer "):
        supplied = authorization[7:].strip()
    if supplied != token:
        log.warning("deny %-15s %s token", ip, "wrong" if supplied else "missing")
        raise HTTPException(status_code=401, detail="invalid or missing token")


def client_dir(request: Request, x_forwarded_for: str | None) -> str:
    """A filesystem-safe directory name derived from a *validated* client IP.

    X-Forwarded-For is attacker-controlled, so it is honored only when
    ``TRUST_PROXY`` is set (i.e. we sit behind a trusted reverse proxy). The
    result is always a parsed ``ipaddress`` value, so it can never contain a
    path separator or traversal sequence.
    """
    raw = request.client.host if request.client else ""
    if _trust_proxy() and x_forwarded_for:
        raw = x_forwarded_for.split(",")[0].strip() or raw
    try:
        ip = ipaddress.ip_address(raw)
    except ValueError:
        return "unknown"
    return str(ip).replace(":", "-")  # ':' from IPv6 -> '-'


def safe_name(name: str, subdir: Path) -> str:
    """Strip path components and keep a filesystem-safe basename."""
    name = os.path.basename(name or "").replace("\\", "_")
    name = re.sub(r"[^A-Za-z0-9._-]", "_", name).strip("._") or "upload"
    if (subdir / name).exists():
        stem, ext = os.path.splitext(name)
        name = f"{stem}-{uuid.uuid4().hex[:8]}{ext}"
    return name


def write_file(name: str, data: bytes, ip: str) -> dict:
    root = _env_upload_dir()
    subdir = (root / ip).resolve()
    # Defense in depth: never let the target escape the upload root.
    if subdir != root and root not in subdir.parents:
        raise HTTPException(status_code=400, detail="invalid destination")
    subdir.mkdir(parents=True, exist_ok=True)
    final = safe_name(name, subdir)
    dest = subdir / final
    with open(dest, "wb") as f:
        f.write(data)
    # Console log only (not surfaced to the web UI).
    log.info("recv %-15s %-30s %10d bytes -> %s", ip, final, len(data), dest)
    return {"saved": final, "dir": ip, "bytes": len(data)}


app = FastAPI(title="File Drop")


@app.get("/", response_class=HTMLResponse)
def index() -> HTMLResponse:
    try:
        return HTMLResponse(INDEX_HTML.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return HTMLResponse("<h1>File Drop</h1><p>POST a file to /upload</p>")


@app.post("/upload")
async def upload(
    request: Request,
    file: UploadFile = File(...),
    authorization: str | None = Header(default=None),
    x_token: str | None = Header(default=None),
    x_forwarded_for: str | None = Header(default=None),
) -> JSONResponse:
    ip = client_dir(request, x_forwarded_for)
    check_auth(authorization, x_token, ip)
    data = await file.read()
    return JSONResponse(write_file(file.filename, data, ip))


@app.api_route("/upload/{filename}", methods=["PUT", "POST"])
async def upload_raw(
    filename: str,
    request: Request,
    authorization: str | None = Header(default=None),
    x_token: str | None = Header(default=None),
    x_forwarded_for: str | None = Header(default=None),
) -> JSONResponse:
    """Raw-body upload (PUT or POST): ``curl --data-binary @x http://host/upload/x``."""
    ip = client_dir(request, x_forwarded_for)
    check_auth(authorization, x_token, ip)
    data = await request.body()
    return JSONResponse(write_file(filename, data, ip))


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "dir": str(_env_upload_dir())}
