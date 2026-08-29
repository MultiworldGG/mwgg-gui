"""Avatar URL safety + uploader helpers.

`safe_avatar_source` is the boundary check applied wherever a remote avatar
URL is about to feed a Kivy widget's `source`. Legacy / hostile URLs collapse
to '' and the widget falls back to its default.

`upload_avatar` and `mint_token` talk to the MWGG webhost's
`/api/avatar/...` endpoints using stdlib only (no `requests` dependency).
"""
from __future__ import annotations

import io
import json
import logging
import mimetypes
import os
import ssl
import threading
import uuid
from typing import Optional, Tuple
from urllib import request
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse

from mwgg_gui.constants import (
    AVATAR_TOKEN_MINT_URL,
    AVATAR_UPLOAD_URL,
    TRUSTED_AVATAR_HOSTS,
)

logger = logging.getLogger("MultiWorld")


# Negative cache for missing avatars: Kivy's Loader re-fetches a 404ing URL
# on every widget rebuild and logs a full traceback each time. The first
# sighting of a URL probes it off-thread; once a probe fails, every later
# safe_avatar_source call collapses to '' (the default avatar) so the Loader
# never retries it this session.
_probe_lock = threading.Lock()
_probe_results: dict[str, bool] = {}
_probes_in_flight: set[str] = set()


def _probe_avatar(url: str) -> None:
    ok = False
    try:
        with request.urlopen(request.Request(url), timeout=10, context=_ssl_context()) as resp:
            resp.read(1)
            ok = True
    except HTTPError as exc:
        logger.info("Avatar %s unavailable (HTTP %s); using the default avatar", url, exc.code)
    except (URLError, OSError) as exc:
        logger.info("Avatar %s unreachable (%s); using the default avatar", url, exc)
    with _probe_lock:
        _probe_results[url] = ok
        _probes_in_flight.discard(url)


def safe_avatar_source(url: str) -> str:
    """Return `url` only if it is HTTPS on the trusted-host allowlist and not
    known to 404; unknown URLs pass optimistically while a probe runs."""
    if not url:
        return ""
    try:
        parsed = urlparse(url)
    except Exception:
        return ""
    if parsed.scheme != "https":
        return ""
    host = (parsed.hostname or "").lower()
    if host not in TRUSTED_AVATAR_HOSTS:
        return ""
    with _probe_lock:
        if _probe_results.get(url) is False:
            return ""
        if url not in _probe_results and url not in _probes_in_flight:
            _probes_in_flight.add(url)
            threading.Thread(
                target=_probe_avatar, args=(url,), name="mwgg-avatar-probe", daemon=True,
            ).start()
    return url


class AvatarUploadError(Exception):
    """Raised when the upload pipeline cannot return a usable URL."""


def _build_multipart(field_name: str, filename: str, mime_type: str, data: bytes) -> Tuple[bytes, str]:
    boundary = f"----mwgg-{uuid.uuid4().hex}"
    parts = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="{field_name}"; filename="{filename}"\r\n'
        f"Content-Type: {mime_type}\r\n\r\n"
    ).encode("utf-8")
    tail = f"\r\n--{boundary}--\r\n".encode("utf-8")
    body = parts + data + tail
    return body, boundary


def _ssl_context() -> ssl.SSLContext:
    return ssl.create_default_context()


def mint_token(timeout: float = 10.0) -> str:
    """POST /api/avatar/token. Returns a UUID string."""
    req = request.Request(AVATAR_TOKEN_MINT_URL, data=b"", method="POST")
    try:
        with request.urlopen(req, timeout=timeout, context=_ssl_context()) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except HTTPError as exc:
        raise AvatarUploadError(f"Token mint failed: HTTP {exc.code}") from exc
    except (URLError, OSError, json.JSONDecodeError) as exc:
        raise AvatarUploadError(f"Token mint failed: {exc}") from exc
    token = payload.get("token", "")
    if not token:
        raise AvatarUploadError("Token mint returned no token")
    return token


def upload_avatar(file_path: str, token: str, timeout: float = 30.0) -> str:
    """POST the file at `file_path` to /api/avatar/upload. Returns the trusted URL.

    The caller is responsible for persisting the returned URL (and the token).
    Runs synchronously -- schedule on a worker thread from the UI.
    """
    if not token:
        raise AvatarUploadError("No avatar token")
    if not os.path.isfile(file_path):
        raise AvatarUploadError(f"File not found: {file_path}")

    with open(file_path, "rb") as f:
        data = f.read()
    if not data:
        raise AvatarUploadError("File is empty")

    mime_type, _ = mimetypes.guess_type(file_path)
    if not mime_type:
        mime_type = "application/octet-stream"
    filename = os.path.basename(file_path) or "avatar"

    body, boundary = _build_multipart("image", filename, mime_type, data)

    req = request.Request(
        AVATAR_UPLOAD_URL,
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "Content-Length": str(len(body)),
        },
    )
    try:
        with request.urlopen(req, timeout=timeout, context=_ssl_context()) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except HTTPError as exc:
        try:
            err_body = json.loads(exc.read().decode("utf-8"))
            err_msg = err_body.get("error", f"HTTP {exc.code}")
        except Exception:
            err_msg = f"HTTP {exc.code}"
        raise AvatarUploadError(err_msg) from exc
    except (URLError, OSError, json.JSONDecodeError) as exc:
        raise AvatarUploadError(f"Upload failed: {exc}") from exc

    url = payload.get("url", "")
    safe = safe_avatar_source(url)
    if not safe:
        raise AvatarUploadError(f"Server returned untrusted URL: {url!r}")
    return safe
