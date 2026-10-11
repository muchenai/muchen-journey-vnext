FROM python:3.14.6-alpine@sha256:26730869004e2b9c4b9ad09cab8625e81d256d1ce97e72df5520e806b1709f92

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app/apps/api:/app/apps/worker

WORKDIR /app

COPY requirements.lock requirements-build.lock ./
RUN python -m pip install --require-hashes -r requirements-build.lock \
    && python -m pip install --require-hashes --no-build-isolation -r requirements.lock \
    && python -m pip check \
    && python -m pip uninstall -y setuptools wheel

ARG TARGETARCH
RUN set -eu; \
    case "${TARGETARCH}" in \
        amd64) alpine_arch=x86_64; libcrypto_sha=161223a16f042b8e469e9441291e071464fd91d4f4bbe6f496ee8d0abd4e0701; libssl_sha=aca521e5ae4a321322a9d47ed64a1775f5ab1ffd215d1e9fc0433c58f7bfd037; openssl_sha=e18c561e6a8fb744b42fe000f4a8cdfcc38e7956e62a6ab44b0a0580db948450 ;; \
        arm64) alpine_arch=aarch64; libcrypto_sha=35b892813c23664a3592e4fc8c12a03538a22c579057655361c7043305272a9a; libssl_sha=d6ec970cc10e01539e41626f720c4e0ac69016eaa2079a10ef776ffd3243db5b; openssl_sha=0d12f4f145ec045dd19e8465bd3cb07b08197f96a3776641511dc2bec53cc0b7 ;; \
        *) echo "Unsupported TARGETARCH: ${TARGETARCH}" >&2; exit 64 ;; \
    esac; \
    base_url="https://dl-cdn.alpinelinux.org/alpine/v3.24/main/${alpine_arch}"; \
    wget -q -O /tmp/libcrypto3.apk "${base_url}/libcrypto3-3.5.8-r0.apk"; \
    wget -q -O /tmp/libssl3.apk "${base_url}/libssl3-3.5.8-r0.apk"; \
    wget -q -O /tmp/openssl.apk "${base_url}/openssl-3.5.8-r0.apk"; \
    printf '%s  %s\n' \
        "${libcrypto_sha}" /tmp/libcrypto3.apk \
        "${libssl_sha}" /tmp/libssl3.apk \
        "${openssl_sha}" /tmp/openssl.apk \
        | sha256sum -c -; \
    apk add --no-network /tmp/libcrypto3.apk /tmp/libssl3.apk /tmp/openssl.apk; \
    rm /tmp/libcrypto3.apk /tmp/libssl3.apk /tmp/openssl.apk

ARG VCS_REF=local
LABEL org.opencontainers.image.source="https://github.com/muchenai2024-creator/muchen-journey-vnext" \
      org.opencontainers.image.title="Muchen Journey vNext Worker" \
      org.opencontainers.image.revision="${VCS_REF}"

COPY pyproject.toml ./
COPY apps/api ./apps/api
COPY apps/worker ./apps/worker

RUN addgroup -S -g 10001 journey \
    && adduser -S -D -H -u 10001 -G journey journey
USER journey

CMD ["python", "-m", "journey_worker.main"]
