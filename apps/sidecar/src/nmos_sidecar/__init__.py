"""NMOS sidecar and worker."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("nmos-sidecar")
except PackageNotFoundError:  # pragma: no cover
    __version__ = "0.0.0"
