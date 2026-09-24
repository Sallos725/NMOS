# 0021 — Google Vertex AI service-account keys for the extraction LLM

Status: accepted, 2026-09-24. Owner request outside the phases (not a Track B feature). New runtime
dependency `google-auth` approved by the owner the same day.

## Context

The extraction LLM is any OpenAI-compatible endpoint called with `Authorization: Bearer <API key>`.
Google Vertex AI has such an endpoint
(`https://aiplatform.googleapis.com/v1/projects/{project}/locations/global/endpoints/openapi`, models
named like `google/gemini-2.5-flash`), but it takes a short-lived OAuth access token (one hour for a
service account), not a fixed key. A pasted token stops working after an hour, so Vertex users could
not use NMOS extraction without running their own token proxy.

## Decision

1. **The API key field takes a service-account JSON key.** When `llm_api_key` (UI or
   `NMOS_LLM_API_KEY`) starts with `{`, it must be a Google service-account key (`"type":
   "service_account"` with `client_email`, `private_key`, `token_uri`). Anything else that starts with
   `{` is rejected when saved, naming what is wrong. Plain keys are unchanged.
2. **The sidecar mints the token.** `vertex.access_token` signs a JWT with the key (scope
   `cloud-platform`), exchanges it at the key's `token_uri`, caches the token per key and refreshes it
   shortly before it expires (google-auth's own margin, under 4 minutes). Extraction runs in the worker,
   so the exchange never sits on the request path. A failed exchange is an `LLMError` like any failed
   call: the job is retried as before.
3. **LLM only.** Embeddings run on the request path with a 300 ms budget, which a token exchange can
   exceed, and Vertex embeddings through the OpenAI-compatible endpoint are unverified. A JSON key in
   `embed_api_key` is rejected when saved.
4. **The key stays a secret.** It is stored and reported like any API key (`api_key_set` only). It is
   not part of any generation key (generations never include credentials); the endpoint URL, which
   names the project, is.
5. **The plugin only fills the URL.** A `Google Vertex AI` preset puts `{project}` in the endpoint, and
   pasting a service-account key fills it from `project_id`. The plugin does not parse or keep anything
   else from the key. A URL still containing `{project}` is rejected when saved.
6. **Transport.** google-auth's bundled transports need `requests` or `urllib3`. A 20-line adapter
   over httpx, which the sidecar already uses, avoids a third HTTP client. `google-auth` pulls in
   `cryptography` and `pyasn1-modules`.

## Consequences

- A Vertex user pastes the key file once and picks a model; nothing else to run.
- A service-account key is a private key and may carry more power than an API key. The guide asks for
  a dedicated service account with only the Vertex AI User role.
- The model list (`GET …/models`) is not expected to work on Vertex; the preset fills a model name.
- Verified with a mocked token endpoint (`tests/test_vertex.py`: signed assertion, caching, refresh,
  failure, config validation). A call against real Vertex needs an owner-supplied key and has not been
  run.
