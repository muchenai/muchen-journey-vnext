FROM node:24.16.0-alpine@sha256:21f403ab171f2dc89bad4dd69d7721bfd15f084ccb46cdd225f31f2bc59b5c9a AS dependencies
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci

FROM node:24.16.0-alpine@sha256:21f403ab171f2dc89bad4dd69d7721bfd15f084ccb46cdd225f31f2bc59b5c9a AS build
WORKDIR /app
ENV NEXT_TELEMETRY_DISABLED=1
COPY --from=dependencies /app/node_modules ./node_modules
COPY . .
RUN npm run build

FROM node:24.16.0-alpine@sha256:21f403ab171f2dc89bad4dd69d7721bfd15f084ccb46cdd225f31f2bc59b5c9a AS runtime
ARG TARGETARCH
ARG VCS_REF=local
LABEL org.opencontainers.image.source="https://github.com/muchenai2024-creator/muchen-journey-vnext" \
      org.opencontainers.image.title="Muchen Journey vNext Web" \
      org.opencontainers.image.revision="${VCS_REF}"
WORKDIR /app
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=3000 \
    HOSTNAME=0.0.0.0
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
RUN rm -rf /usr/local/lib/node_modules/npm \
    /usr/local/bin/npm \
    /usr/local/bin/npx
RUN addgroup --system --gid 1001 nodejs && adduser --system --uid 1001 nextjs
COPY --from=build --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=build --chown=nextjs:nodejs /app/.next/static ./.next/static
COPY --from=build --chown=nextjs:nodejs /app/public ./public
USER nextjs
EXPOSE 3000
CMD ["node", "server.js"]
