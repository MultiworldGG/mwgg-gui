"""URL-scheme image loaders for the MultiworldGG client.

Kivy's :class:`~kivy.core.image.ImageLoader` dispatches purely on filename
extension and has no notion of URL schemes. World clients (Universal Tracker
in particular) need ``ap:`` and ``ap:zip:`` prefixes that resolve via
:func:`importlib.resources` (apworld-bundled resources, including zipimport)
and :mod:`zipfile` (external poptracker packs). Kivy's :func:`ImageLoader.register`
only appends a class to ``ImageLoader.loaders`` for extension-based dispatch,
so it isn't enough on its own — but it's the right hook to combine with a
small scheme-dispatch table installed by patching ``ImageLoader.load`` exactly
once.

This module exposes a single public API, :func:`register_url_scheme`, and
registers ``ap:zip:`` and ``ap:`` at import time. Importing
:mod:`mwgg_gui` is enough to make AsyncImage understand both prefixes.
"""
from __future__ import annotations

import importlib.resources
import io
import logging
import typing
import zipfile

from kivy.core.image import ImageLoader, ImageLoaderBase, ImageData
from kivy.uix.image import AsyncImage

logger = logging.getLogger("Client")

__all__ = (
    "ApAsyncImage",
    "ApPkgImageLoader",
    "ApZipImageLoader",
    "register_url_scheme",
)


# Prefix -> loader class. Order matters: scheme dispatch checks each entry in
# insertion order so longer/more-specific prefixes (e.g. "ap:zip:") must be
# registered BEFORE shorter ones (e.g. "ap:") to avoid the short prefix
# greedy-matching everything.
_scheme_loaders: "dict[str, type[ImageLoaderBase]]" = {}


def _bytes_to_image_data(data: bytes | bytearray) -> typing.List[ImageData]:
    """Decode raw image bytes via whichever of Kivy's registered loaders can
    accept an in-memory buffer (img_sdl2, img_pil, ...)."""
    buf = io.BytesIO(data)
    for loader_cls in ImageLoader.loaders:
        if loader_cls.can_load_memory():
            return loader_cls.load(loader_cls, buf)
    raise RuntimeError("No Kivy image loader can decode from memory")


class ApPkgImageLoader(ImageLoaderBase):
    """``ap:<dotted.module>/<resource path>`` — loads via
    :func:`importlib.resources.files`. Works uniformly for folder-installed
    and zipimport-installed (``.apworld``) packages without touching the
    deprecated :mod:`pkgutil` API.
    """

    def load(self, filename: str) -> typing.List[ImageData]:
        try:
            payload = filename[len("ap:"):]
            module, _, resource = payload.partition("/")
            if not module or not resource:
                raise ValueError(f"ap: URL must be ap:<module>/<path>, got {filename!r}")
            ref = importlib.resources.files(module)
            for part in resource.split("/"):
                ref = ref.joinpath(part)
            data = ref.read_bytes()
            return _bytes_to_image_data(data)
        except Exception:
            logger.exception(f"ApPkgImageLoader failed for {filename!r}")
            raise


class ApZipImageLoader(ImageLoaderBase):
    """``ap:zip:<absolute zipfile path>/<internal path>`` — opens the zip on
    disk and reads the internal entry.

    The zipfile path may itself contain ``/`` or ``\\`` separators (Unix or
    Windows). We anchor the split on the literal ``.zip`` extension so the
    remaining slashed text is treated as a path inside the archive.
    """

    def load(self, filename: str) -> typing.List[ImageData]:
        try:
            payload = filename[len("ap:zip:"):]
            normalized = payload.replace("\\", "/").lower()
            anchor = normalized.find(".zip/")
            if anchor == -1:
                # Last-ditch split — works iff the internal path has no slashes.
                zip_path, internal = payload.rsplit("/", 1)
            else:
                cut = anchor + len(".zip")
                zip_path = payload[:cut]
                internal = payload[cut + 1:].replace("\\", "/")
            with zipfile.ZipFile(zip_path) as zf:
                data = zf.read(internal)
            return _bytes_to_image_data(data)
        except Exception:
            logger.exception(f"ApZipImageLoader failed for {filename!r}")
            raise


class ApAsyncImage(AsyncImage):
    """AsyncImage subclass that recognizes ``ap:`` and ``ap:zip:`` URLs.

    Stock :meth:`AsyncImage.is_uri` only accepts http/https/ftp/smb; anything
    else is treated as a local filesystem path, which makes AsyncImage take a
    synchronous CoreImage path and (because the file doesn't actually exist
    at the URL's textual location) emit ``AsyncImage: Not found`` even when
    our scheme dispatch would otherwise resolve it. Overriding ``is_uri`` so
    ``ap:`` counts as a URI sends the load through Kivy's ``Loader`` thread
    pool, which is what we want for large pack images.
    """

    def is_uri(self, filename: str) -> bool:
        if filename.startswith("ap:"):
            return True
        return super().is_uri(filename)


def register_url_scheme(prefix: str, loader_class: type[ImageLoaderBase]) -> None:
    """Register a custom URL scheme with Kivy's :class:`ImageLoader`.

    :param prefix: String prefix that identifies the scheme, including the
        trailing colon. Examples: ``"ap:"``, ``"ap:zip:"``, ``"vfs://"``.
        Order matters — register longer/more-specific prefixes first.
    :param loader_class: A :class:`~kivy.core.image.ImageLoaderBase` subclass
        whose ``load(filename)`` resolves the URL to image data. The class is
        constructed each time a matching URL is loaded.

    Internally this both calls :func:`ImageLoader.register` (so the class is
    visible to Kivy's loader list) and installs a one-time wrapper around
    :func:`ImageLoader.load` that consults the scheme dispatch table BEFORE
    Kivy's extension-based dispatch. Calling this twice with the same prefix
    overwrites the previous registration.
    """
    if prefix in _scheme_loaders:
        # Replace existing — common during hot-reload / re-imports.
        if loader_class is not _scheme_loaders[prefix]:
            logger.debug(f"Replacing image loader for scheme {prefix!r}")
    else:
        _scheme_loaders[prefix] = loader_class
    _scheme_loaders[prefix] = loader_class
    ImageLoader.register(loader_class)
    _install_scheme_dispatch()


def _install_scheme_dispatch() -> None:
    """Patch ``ImageLoader.load`` exactly once so URL prefixes route to our
    custom loaders before Kivy's extension-based dispatch runs."""
    if getattr(ImageLoader.load, "_mwgg_scheme_dispatch", False):
        return
    original_load = ImageLoader.load

    def dispatch(filename: str, default_load=original_load, **kwargs):
        # Iterate in insertion order so "ap:zip:" wins over "ap:" without
        # forcing callers to manage prefix ordering manually.
        for prefix, loader_cls in _scheme_loaders.items():
            if filename.startswith(prefix):
                return loader_cls(filename)
        return default_load(filename, **kwargs)

    dispatch._mwgg_scheme_dispatch = True  # type: ignore[attr-defined]
    ImageLoader.load = dispatch


# Built-in schemes. ap:zip: MUST be registered first so it doesn't lose to
# the broader "ap:" prefix.
register_url_scheme("ap:zip:", ApZipImageLoader)
register_url_scheme("ap:", ApPkgImageLoader)
