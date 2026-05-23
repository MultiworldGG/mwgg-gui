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


def safe_avatar_source(url: str) -> str:
    """Return `url` only if it is HTTPS on the trusted-host allowlist."""
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
    Runs synchronously — schedule on a worker thread from the UI.
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
