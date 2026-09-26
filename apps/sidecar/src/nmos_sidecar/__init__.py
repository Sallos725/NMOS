"""NMOS sidecar and worker."""

from importlib.metadata import PackageNotFoundError, version

from psycopg.types.json import set_json_dumps

from .canonical import storable_json

try:
    __version__ = version("nmos-sidecar")
except PackageNotFoundError:  # pragma: no cover
    __version__ = "0.0.0"

# Every jsonb value this process writes (manifests, metadata, traces, config) drops lone surrogates (ADR 0029).
set_json_dumps(storable_json)
