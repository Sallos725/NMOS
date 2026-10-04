"""Probe Vertex AI's publisher-model catalog with a service-account key (ADR 0022 amendment 1).

Read-only: it mints an access token with the sidecar's own code and lists `publishers/google/models`, which
calls no model and costs nothing. It prints HTTP statuses, counts and model names only, never the key or the
token. Each variant answers one question the sidecar's model list depends on: does the global host serve the
catalog, and is the `x-goog-user-project` header needed?

    cd apps/sidecar && uv run python ../../tools/vertex_catalog_probe.py /path/to/service-account.json
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import httpx

from nmos_sidecar import vertex


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    info = vertex.service_account_info(Path(sys.argv[1]).read_text(encoding="utf-8"))
    if info is None:
        print("not a service-account key")
        return 2
    token = vertex.access_token(info)
    project = info.get("project_id", "")
    variants = [
        ("global, with x-goog-user-project", "https://aiplatform.googleapis.com", True),
        ("global, without the header", "https://aiplatform.googleapis.com", False),
        ("us-central1, with x-goog-user-project", "https://us-central1-aiplatform.googleapis.com", True),
    ]
    for label, host, with_project in variants:
        headers = {"Authorization": f"Bearer {token}"}
        if with_project:
            headers["x-goog-user-project"] = project
        rows, token_page, status, error = [], None, 0, ""
        for _ in range(20):
            params = {"pageSize": 100, **({"pageToken": token_page} if token_page else {})}
            res = httpx.get(f"{host}/v1beta1/publishers/google/models", headers=headers, params=params, timeout=30)
            status = res.status_code
            if status != 200:
                error = res.text[:300]
                break
            body = res.json()
            rows += body.get("publisherModels", [])
            token_page = body.get("nextPageToken")
            if not token_page:
                break
        print(f"\n== {label}: HTTP {status}, {len(rows)} models")
        if error:
            print("  ", error.replace(token, "<token>"))
            continue
        gemini = sorted(
            (r["name"].rsplit("/", 1)[-1], r.get("launchStage", "?"), ",".join(sorted(r.get("supportedActions") or {})))
            for r in rows if r.get("name", "").rsplit("/", 1)[-1].startswith("gemini"))
        print(f"   gemini*: {len(gemini)}")
        for name, stage, actions in gemini:
            print(f"   {name:48} {stage:14} {actions}")
    print("\nmodel names only; no key or token was printed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
