FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.10 /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PROJECT_ENVIRONMENT=/opt/venv PATH="/opt/venv/bin:$PATH"

WORKDIR /app/apps/sidecar
COPY apps/sidecar/pyproject.toml apps/sidecar/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY apps/sidecar/src ./src
RUN uv sync --frozen --no-dev

COPY migrations /app/migrations
ENV NMOS_MIGRATIONS_DIR=/app/migrations
# The plugin of the same commit (ADR 0037): the sidecar tells whether the plugin in use is this build.
COPY adapters/pocketrisu-plugin/dist/nmos-pocketrisu.js /app/plugin/nmos-pocketrisu.js
ENV NMOS_PLUGIN_FILE=/app/plugin/nmos-pocketrisu.js

RUN useradd --system --uid 10001 nmos
USER nmos
EXPOSE 8790
CMD ["sh", "-c", "nmos-migrate && exec uvicorn nmos_sidecar.api:app_factory --factory --host 0.0.0.0 --port 8790"]
