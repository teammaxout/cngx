# cngx local proxy, optional container for home server / VPS
#
# Runs the ASGI reverse proxy only (not a multi-service SaaS stack).
# Forwards LLM traffic, fingerprints on the side. API keys via env at runtime.
#
# Build:  docker build -t cngx-proxy .
# Run:    docker run -p 8642:8642 -e OPENAI_API_KEY=sk-... cngx-proxy
#
# See README.md and SECURITY.md for key handling (memory only, never logged).

FROM python:3.11-slim AS builder

WORKDIR /build
RUN pip install --no-cache-dir hatchling
COPY pyproject.toml README.md LICENSE ./
COPY cngx/ cngx/
RUN pip wheel --no-deps --wheel-dir /wheels .

FROM python:3.11-slim

LABEL maintainer="cngx Contributors"
LABEL description="cngx local LLM proxy with behavioral fingerprinting"
LABEL version="0.1.4"

RUN groupadd -r cngx && useradd -r -g cngx -d /app -s /sbin/nologin cngx

WORKDIR /app
COPY --from=builder /wheels /wheels
RUN pip install --no-cache-dir /wheels/*.whl && rm -rf /wheels

RUN mkdir -p /data/.cngx && chown -R cngx:cngx /data
USER cngx

ENV CNGX_STORAGE_DIR=/data/.cngx
ENV CNGX_PROXY_HOST=0.0.0.0
ENV CNGX_PROXY_PORT=8642
ENV PYTHONUNBUFFERED=1

EXPOSE 8642

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD python -c "import httpx; httpx.get('http://127.0.0.1:8642/health').raise_for_status()" || exit 1

CMD ["uvicorn", "cngx.proxy.app:app", "--host", "0.0.0.0", "--port", "8642"]
