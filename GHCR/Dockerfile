# syntax=docker/dockerfile:1.7

ARG NODE_IMAGE=node:22-alpine
ARG PYTHON_IMAGE=python:3.12-slim

FROM ${NODE_IMAGE} AS studio-builder

WORKDIR /build/studio

COPY studio/package.json studio/package-lock.json ./
RUN npm ci

COPY studio/ ./
RUN npm run build


FROM ${PYTHON_IMAGE} AS wheel-builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /build

COPY pyproject.toml MANIFEST.in README.md LICENSE ./
COPY hydra_etl/ ./hydra_etl/
COPY --from=studio-builder /build/studio/dist/ ./hydra_etl/studio_dist/

RUN python -m pip install --upgrade pip build \
    && python -m pip wheel \
       --wheel-dir /wheels \
       ".[server,duckdb,parquet,mysql,postgres,mongodb,http]"


FROM ${PYTHON_IMAGE} AS runtime

ARG HYDRA_UID=10001
ARG HYDRA_GID=10001

LABEL org.opencontainers.image.title="Hydra ETL" \
      org.opencontainers.image.description="Declarative ETL engine, CLI, API, and visual Studio" \
      org.opencontainers.image.source="https://github.com/bejaouibechir/Hydra" \
      org.opencontainers.image.url="https://hydraetl.com" \
      org.opencontainers.image.licenses="AGPL-3.0-or-later"

ENV HYDRA_WORKSPACE=/workspace \
    HYDRA_LANG=en \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

RUN groupadd --gid "${HYDRA_GID}" hydra \
    && useradd --uid "${HYDRA_UID}" --gid "${HYDRA_GID}" \
       --create-home --home-dir /home/hydra hydra \
    && mkdir -p /workspace \
    && chown -R hydra:hydra /workspace /home/hydra

COPY --from=wheel-builder /wheels/ /wheels/
RUN python -m pip install \
      --no-index \
      --find-links=/wheels \
      "hydra-etl[server,duckdb,parquet,mysql,postgres,mongodb,http]" \
    && rm -rf /wheels

WORKDIR /workspace
USER hydra

EXPOSE 5678

HEALTHCHECK --interval=10s --timeout=3s --start-period=20s --retries=5 \
  CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:5678/api/health', timeout=2).read()"]

CMD ["hdrctl", "serve", "--host", "0.0.0.0", "--port", "5678", "--workspace", "/workspace"]
