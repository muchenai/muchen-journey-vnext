FROM python:3.14.6-alpine@sha256:26730869004e2b9c4b9ad09cab8625e81d256d1ce97e72df5520e806b1709f92

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app/apps/api:/app/apps/worker

WORKDIR /app

# Generate and normalize persisted AI Academy covers without external media services.
RUN apk add --no-cache ffmpeg=8.1.3-r0

COPY requirements.lock requirements-build.lock ./
RUN python -m pip install --require-hashes -r requirements-build.lock \
    && python -m pip install --require-hashes --no-build-isolation -r requirements.lock \
    && python -m pip check \
    && python -m pip uninstall -y setuptools wheel

ARG TARGETARCH
RUN set -eu; \
    case "${TARGETARCH}" in \
        amd64) alpine_arch=x86_64; libcrypto_sha=042026082cc9bc7872d1baa81755c50efa70b05f03b5369fdc5f0a1303009720; libssl_sha=18c5778cbe52e1991303f8531970b05d4e6e036ea08349322f7422f42a689dc7; openssl_sha=ed11241475e5757ce8eb9788b18116a804a579395d4813605df12989a2acbabf ;; \
        arm64) alpine_arch=aarch64; libcrypto_sha=58ea027d8bd64fffac7d2106a9034341d6735387298a5e01b551429c73a13c71; libssl_sha=4aff30f84e7ac922b026f8b2dd574d91bb3bb01d22767a8a9a0a10c5ef64a44b; openssl_sha=4f5adffa94887a87807d9222cf26930e906ae47e6a15ee9b8d1da034d695614d ;; \
        *) echo "Unsupported TARGETARCH: ${TARGETARCH}" >&2; exit 64 ;; \
    esac; \
    base_url="https://dl-cdn.alpinelinux.org/alpine/v3.24/main/${alpine_arch}"; \
    wget -q -O /tmp/libcrypto3.apk "${base_url}/libcrypto3-3.5.9-r1.apk"; \
    wget -q -O /tmp/libssl3.apk "${base_url}/libssl3-3.5.9-r1.apk"; \
    wget -q -O /tmp/openssl.apk "${base_url}/openssl-3.5.9-r1.apk"; \
    printf '%s  %s\n' \
        "${libcrypto_sha}" /tmp/libcrypto3.apk \
        "${libssl_sha}" /tmp/libssl3.apk \
        "${openssl_sha}" /tmp/openssl.apk \
        | sha256sum -c -; \
    apk add --no-network /tmp/libcrypto3.apk /tmp/libssl3.apk /tmp/openssl.apk; \
    rm /tmp/libcrypto3.apk /tmp/libssl3.apk /tmp/openssl.apk

ARG VCS_REF=local
LABEL org.opencontainers.image.source="https://github.com/muchenai2024-creator/muchen-journey-vnext" \
      org.opencontainers.image.title="Muchen Journey vNext API" \
      org.opencontainers.image.revision="${VCS_REF}"

COPY pyproject.toml ./
COPY apps/api ./apps/api
COPY apps/worker ./apps/worker
COPY migrations ./migrations
COPY alembic.ini ./
COPY contracts ./contracts
COPY config ./config
COPY deploy/staging/deploy.sh ./deploy/staging/deploy.sh
RUN chmod 0555 contracts && chmod 0444 contracts/openapi.json deploy/staging/deploy.sh
COPY tests ./tests
COPY scripts ./scripts

RUN addgroup -S -g 10001 journey \
    && adduser -S -D -H -u 10001 -G journey journey
USER journey

CMD ["uvicorn", "journey_api.main:app", "--host", "0.0.0.0", "--port", "8000"]
