#!/bin/sh
# NMOS portable: start Postgres, the sidecar and the worker. Ctrl+C stops all of them.
cd "$(dirname "$0")" || exit 1
exec ./python/bin/python3 nmos_launcher.py "$@"
