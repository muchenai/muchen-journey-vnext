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
