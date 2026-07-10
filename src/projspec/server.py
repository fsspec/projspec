"""
projspec HTTP server
====================
A lightweight FastAPI server that exposes all projspec and filebrowser
operations as JSON endpoints.  It is intended to run as a long-lived
background process owned by the VS Code extension so that repeated
subprocess-spawn overhead is eliminated.

Start with::

    projspec serve [--port PORT] [--host HOST]

The server binds to localhost only by default so it is not exposed on
the network.  The extension discovers the port via the ``--port-file``
option, which writes the chosen port number to a file that the TypeScript
client can read.

Endpoints
---------
GET  /ping                       → {"ok": true}
GET  /info                       → class_infos() JSON
GET  /enum_members               → {snake_name: {MEMBER: value}} JSON
GET  /library                    → {url: project_dict, ...}
POST /library/delete             → {"url": url}
POST /scan                       → {"path": str, "add_to_library": bool, "storage_options": str|null}
POST /create                     → {"spec": str, "path": str}

POST /filebrowser/browse         → {"url": str, "storage_options": obj|null}
POST /filebrowser/inspect        → {"url": str, "storage_options": obj|null}
POST /filebrowser/inspect_as_project → {"url": str, "storage_options": obj|null}
POST /filebrowser/scan_directory → {"url": str, "storage_options": obj|null}
POST /filebrowser/read_file      → {"url": str, "storage_options": obj|null, "max_bytes": int|null}
POST /filebrowser/write_file     → {"url": str, "content": str, "storage_options": obj|null}
POST /filebrowser/delete         → {"url": str, "storage_options": obj|null, "recursive": bool}
POST /filebrowser/move           → {"src": str, "dst": str, "storage_options": obj|null}
POST /filebrowser/copy           → {"src": str, "dst": str, "storage_options": obj|null, "confirmed": bool}
POST /filebrowser/mkdir          → {"url": str, "storage_options": obj|null}
POST /filebrowser/add_to_library → {"url": str, "storage_options": obj|null}
GET  /filebrowser/protocols      → [str, ...]
GET  /filebrowser/bookmarks      → [{url, label, storage_options?}, ...]
POST /filebrowser/bookmarks/add  → {"url": str, "label": str, "storage_options": obj|null}
POST /filebrowser/bookmarks/remove → {"url": str}
"""

from __future__ import annotations

from contextlib import asynccontextmanager
import hmac
import json
import logging
import os
import threading
import time
from pathlib import Path
from typing import Any

try:
    from fastapi import FastAPI, Request
    from fastapi.responses import JSONResponse
    from pydantic import BaseModel
except ImportError as _e:  # pragma: no cover
    raise ImportError(
        "projspec server requires 'fastapi' and 'uvicorn'.  "
        "Install them with:  pip install 'projspec[serve]'"
    ) from _e

# ---------------------------------------------------------------------------
# File-based logger — writes to the projspec config dir so the PyCharm and
# VS Code plugins can read the same file as the Python-side server logs.
# ---------------------------------------------------------------------------


def _log_path() -> Path:
    conf_dir = Path(
        os.environ.get("PROJSPEC_CONFIG_DIR", Path.home() / ".config" / "projspec")
    )
    conf_dir.mkdir(parents=True, exist_ok=True)
    return conf_dir / "server.log"


def _setup_logging() -> logging.Logger:
    logger = logging.getLogger("projspec.server")
    logger.setLevel(logging.DEBUG)
    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
    )
    fh = logging.FileHandler(_log_path(), mode="a", encoding="utf-8")
    fh.setFormatter(fmt)
    logger.addHandler(fh)
    sh = logging.StreamHandler()
    sh.setFormatter(fmt)
    logger.addHandler(sh)
    return logger


_log = _setup_logging()

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(title="projspec", docs_url=None, redoc_url=None)

# ---------------------------------------------------------------------------
# Bearer-token auth — set by run() when the server is started with a token.
# Every endpoint except GET /ping requires "Authorization: Bearer <token>".
# ---------------------------------------------------------------------------
_TOKEN: str | None = None


@app.middleware("http")
async def _auth_check(request: Request, call_next):
    """Reject requests without a valid bearer token (except /ping)."""
    if _TOKEN and request.url.path != "/ping":
        expected = f"Bearer {_TOKEN}"
        supplied = request.headers.get("authorization", "")
        if not hmac.compare_digest(supplied, expected):
            return JSONResponse(status_code=401, content={"error": "unauthorized"})
    return await call_next(request)


@app.middleware("http")
async def _log_requests(request: Request, call_next):
    """Log every request and response with timing."""
    t0 = time.monotonic()
    _log.info(
        "REQ  %s %s body=%db",
        request.method,
        request.url.path,
        int(request.headers.get("content-length", 0)),
    )
    try:
        response = await call_next(request)
        ms = int((time.monotonic() - t0) * 1000)
        _log.info(
            "RESP %s %s -> %d (%dms)",
            request.method,
            request.url.path,
            response.status_code,
            ms,
        )
        return response
    except Exception as exc:
        ms = int((time.monotonic() - t0) * 1000)
        _log.error(
            "ERR  %s %s -> exception %s (%dms)",
            request.method,
            request.url.path,
            exc,
            ms,
        )
        raise


# Serialise to JSON ourselves so NaN/Infinity in Python floats become null
# (the default FastAPI JSONResponse would raise on those).
def _json(obj: Any, **kw) -> JSONResponse:
    return JSONResponse(content=json.loads(json.dumps(obj, default=str)))


# ---------------------------------------------------------------------------
# Shared state — loaded lazily and cached for the lifetime of the server
# ---------------------------------------------------------------------------

_info_cache: dict | None = None
_info_lock = threading.Lock()

_enum_cache: dict | None = None
_enum_lock = threading.Lock()


def _get_info() -> dict:
    global _info_cache
    with _info_lock:
        if _info_cache is None:
            from projspec.utils import class_infos

            _info_cache = class_infos()
        return _info_cache


def _get_enum_members() -> dict:
    global _enum_cache
    with _enum_lock:
        if _enum_cache is None:
            import importlib
            import pkgutil
            import projspec.content
            import projspec.artifact
            import projspec.utils as pu
            from projspec.utils import camel_to_snake

            for pkg in (projspec.content, projspec.artifact):
                for m in pkgutil.iter_modules(pkg.__path__, pkg.__name__ + "."):
                    importlib.import_module(m.name)

            out: dict = {}
            seen: set = set()

            def walk(cls):
                for sub in cls.__subclasses__():
                    if sub in seen:
                        continue
                    seen.add(sub)
                    walk(sub)
                    try:
                        out[camel_to_snake(sub.__name__)] = {
                            m.name: m.value for m in sub
                        }
                    except TypeError:
                        pass  # not an enum

            walk(pu.Enum)
            _enum_cache = out
        return _enum_cache


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------


@app.get("/ping")
def ping():
    return {"ok": True}


# ---------------------------------------------------------------------------
# projspec core
# ---------------------------------------------------------------------------


@app.get("/info")
def get_info():
    return _json(_get_info())


@app.get("/enum_members")
def get_enum_members():
    return _json(_get_enum_members())


@app.get("/library")
def get_library():
    from projspec.library import ProjectLibrary

    lib = ProjectLibrary()
    return _json({k: v.to_dict(compact=False) for k, v in lib.entries.items()})


class LibraryDeleteRequest(BaseModel):
    url: str


@app.post("/library/delete")
def library_delete(req: LibraryDeleteRequest):
    from projspec.library import ProjectLibrary

    lib = ProjectLibrary()
    lib.entries.pop(req.url, None)
    lib.save()
    return {"ok": True}


class ScanRequest(BaseModel):
    path: str
    add_to_library: bool = False
    storage_options: str | None = None


@app.post("/scan")
def do_scan(req: ScanRequest):
    from projspec.utils import scan_glob

    so = req.storage_options or ""
    results = []
    for proj in scan_glob(
        req.path,
        storage_options=so,
        add_to_library=req.add_to_library,
    ):
        try:
            results.append(proj.to_dict(compact=False))
        except Exception as exc:
            results.append({"error": str(exc)})
    return _json({"results": results, "code": 0})


class CreateRequest(BaseModel):
    spec: str
    path: str


@app.post("/create")
def do_create(req: CreateRequest):
    from projspec.proj import Project
    from projspec.proj.base import registry

    if req.spec not in registry:
        return _json({"error": f"Unknown spec type: {req.spec}", "code": 1})
    proj = Project(req.path)
    if req.spec in proj:
        return _json({"error": f"Project already has a {req.spec} spec", "code": 1})
    try:
        files = proj.create(req.spec)
        return _json({"files": list(files), "code": 0})
    except Exception as exc:
        return _json({"error": str(exc), "code": 1})


# ---------------------------------------------------------------------------
# Filebrowser — request models
# ---------------------------------------------------------------------------


class UrlSoRequest(BaseModel):
    url: str
    storage_options: dict | None = None


class ReadFileRequest(BaseModel):
    url: str
    storage_options: dict | None = None
    max_bytes: int | None = None


class WriteFileRequest(BaseModel):
    url: str
    content: str
    storage_options: dict | None = None


class DeleteRequest(BaseModel):
    url: str
    storage_options: dict | None = None
    recursive: bool = False


class MoveRequest(BaseModel):
    src: str
    dst: str
    storage_options: dict | None = None


class CopyRequest(BaseModel):
    src: str
    dst: str
    storage_options: dict | None = None
    confirmed: bool = False


class BookmarkAddRequest(BaseModel):
    url: str
    label: str = ""
    storage_options: dict | None = None


class BookmarkRemoveRequest(BaseModel):
    url: str


# ---------------------------------------------------------------------------
# Filebrowser — endpoints
# ---------------------------------------------------------------------------


@app.post("/filebrowser/browse")
def fb_browse(req: UrlSoRequest):
    from projspec.filebrowser import browse

    return _json(browse(req.url, storage_options=req.storage_options))


@app.post("/filebrowser/inspect")
def fb_inspect(req: UrlSoRequest):
    from projspec.filebrowser import inspect_file

    return _json(inspect_file(req.url, storage_options=req.storage_options))


@app.post("/filebrowser/inspect_as_project")
def fb_inspect_as_project(req: UrlSoRequest):
    from projspec.filebrowser import inspect_as_project

    return _json(inspect_as_project(req.url, storage_options=req.storage_options))


@app.post("/filebrowser/scan_directory")
def fb_scan_directory(req: UrlSoRequest):
    from projspec.filebrowser import scan_directory

    return _json(scan_directory(req.url, storage_options=req.storage_options))


@app.post("/filebrowser/read_file")
def fb_read_file(req: ReadFileRequest):
    from projspec.filebrowser import read_file

    kwargs: dict = {"storage_options": req.storage_options}
    if req.max_bytes is not None:
        kwargs["max_bytes"] = req.max_bytes
    return _json(read_file(req.url, **kwargs))


@app.post("/filebrowser/write_file")
def fb_write_file(req: WriteFileRequest):
    from projspec.filebrowser import write_file

    return _json(write_file(req.url, req.content, storage_options=req.storage_options))


@app.post("/filebrowser/delete")
def fb_delete(req: DeleteRequest):
    from projspec.filebrowser import delete

    return _json(
        delete(req.url, storage_options=req.storage_options, recursive=req.recursive)
    )


@app.post("/filebrowser/move")
def fb_move(req: MoveRequest):
    from projspec.filebrowser import move

    return _json(move(req.src, req.dst, storage_options=req.storage_options))


@app.post("/filebrowser/copy")
def fb_copy(req: CopyRequest):
    from projspec.filebrowser import copy

    return _json(
        copy(
            req.src,
            req.dst,
            storage_options=req.storage_options,
            confirmed=req.confirmed,
        )
    )


@app.post("/filebrowser/mkdir")
def fb_mkdir(req: UrlSoRequest):
    from projspec.filebrowser import mkdir

    return _json(mkdir(req.url, storage_options=req.storage_options))


@app.post("/filebrowser/add_to_library")
def fb_add_to_library(req: UrlSoRequest):
    from projspec.filebrowser import add_to_projspec_library

    return _json(add_to_projspec_library(req.url, storage_options=req.storage_options))


@app.get("/filebrowser/protocols")
def fb_protocols():
    from projspec.filebrowser import supported_protocols

    return _json(supported_protocols())


@app.get("/filebrowser/bookmarks")
def fb_bookmarks():
    from projspec.filebrowser import bookmarks_list

    return _json(bookmarks_list())


@app.post("/filebrowser/bookmarks/add")
def fb_bookmark_add(req: BookmarkAddRequest):
    from projspec.filebrowser import bookmark_add

    return _json(
        bookmark_add(req.url, label=req.label, storage_options=req.storage_options)
    )


@app.post("/filebrowser/bookmarks/remove")
def fb_bookmark_remove(req: BookmarkRemoveRequest):
    from projspec.filebrowser import bookmark_remove

    return _json(bookmark_remove(req.url))


# ---------------------------------------------------------------------------
# Entrypoint (used by `projspec serve`)
# ---------------------------------------------------------------------------


def _generate_self_signed_cert() -> tuple[bytes, str, str]:
    """Generate an ephemeral self-signed TLS cert+key for 127.0.0.1/localhost.

    Returns ``(cert_der, cert_path, key_path)``: ``cert_der`` is the raw
    DER-encoded certificate (published hex-encoded via the port file so that
    pinned clients — the VS Code extension and the PyCharm plugin — can trust
    it without a real CA); ``cert_path``/``key_path`` are PEM files on disk
    suitable for uvicorn's ``ssl_certfile``/``ssl_keyfile``.
    """
    import datetime
    import ipaddress
    import tempfile

    try:
        from cryptography import x509
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.x509.oid import NameOID
    except ImportError as exc:  # pragma: no cover
        raise ImportError(
            "projspec server requires 'cryptography' to generate its TLS "
            "certificate.  Install it with:  pip install 'projspec[serve]'"
        ) from exc

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "projspec-server")])
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(minutes=5))
        .not_valid_after(now + datetime.timedelta(days=825))
        .add_extension(
            x509.SubjectAlternativeName(
                [
                    x509.DNSName("localhost"),
                    x509.IPAddress(ipaddress.ip_address("127.0.0.1")),
                    x509.IPAddress(ipaddress.ip_address("::1")),
                ]
            ),
            critical=False,
        )
        .sign(key, hashes.SHA256())
    )

    cert_der = cert.public_bytes(serialization.Encoding.DER)
    cert_pem = cert.public_bytes(serialization.Encoding.PEM)
    key_pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    )

    cert_fh = tempfile.NamedTemporaryFile(
        suffix=".pem", prefix="projspec-cert-", delete=False
    )
    cert_fh.write(cert_pem)
    cert_fh.close()
    key_fh = tempfile.NamedTemporaryFile(
        suffix=".pem", prefix="projspec-key-", delete=False
    )
    key_fh.write(key_pem)
    key_fh.close()
    os.chmod(key_fh.name, 0o600)

    return cert_der, cert_fh.name, key_fh.name


def run(
    host: str = "127.0.0.1",
    port: int = 0,
    port_file: str | None = None,
    token: str | None = None,
) -> None:
    """Start the uvicorn server over HTTPS with an ephemeral self-signed cert.

    If ``token`` is given, every endpoint other than ``GET /ping`` requires
    an ``Authorization: Bearer <token>`` header.  The port file (if given)
    is written as ``"https:<port>:<token>:<certHex>"`` once the server is
    ready — ``certHex`` is the hex-encoded DER certificate, allowing callers
    to pin it rather than trusting a real CA.
    """
    import atexit
    import socket

    import uvicorn

    global _TOKEN
    _TOKEN = token or None

    if port == 0:
        with socket.socket() as s:
            s.bind((host, 0))
            port = s.getsockname()[1]

    cert_der, cert_path, key_path = _generate_self_signed_cert()

    def _cleanup_cert_files() -> None:
        for p in (cert_path, key_path):
            try:
                os.unlink(p)
            except OSError:
                pass

    atexit.register(_cleanup_cert_files)

    _log.info("SERVER starting on https://%s:%d — log: %s", host, port, _log_path())

    if port_file:
        os.makedirs(os.path.dirname(os.path.abspath(port_file)), exist_ok=True)
        with open(port_file, "w") as fh:
            fh.write(f"https:{port}:{token or ''}:{cert_der.hex()}")
        _log.info("SERVER port file written: %s", port_file)

    try:
        uvicorn.run(
            app,
            host=host,
            port=port,
            log_level="info",
            ssl_certfile=cert_path,
            ssl_keyfile=key_path,
        )
    finally:
        _cleanup_cert_files()


def main() -> None:
    """Console-script entry point for the ``projspec-server`` command.

    Accepts the same arguments as :func:`run` via the command line::

        projspec-server [--host HOST] [--port PORT] [--port-file PATH] [--token TOKEN]

    Defaults: host=127.0.0.1, port=0 (free port chosen automatically).
    """
    import argparse

    parser = argparse.ArgumentParser(
        prog="projspec-server",
        description="Start the projspec HTTP server (requires fastapi + uvicorn).",
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Interface to bind to (default: 127.0.0.1)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=0,
        help="TCP port; 0 picks a free port automatically (default: 0)",
    )
    parser.add_argument(
        "--port-file",
        default=None,
        metavar="PATH",
        help="Write the chosen port number to this file once the server is ready",
    )
    parser.add_argument(
        "--token",
        default=None,
        help=(
            "Bearer token required in the Authorization header for all "
            "endpoints except /ping.  If omitted, no authentication is "
            "required."
        ),
    )
    args = parser.parse_args()
    run(host=args.host, port=args.port, port_file=args.port_file, token=args.token)


if __name__ == "__main__":
    main()
