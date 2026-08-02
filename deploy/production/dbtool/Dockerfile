FROM docker.io/library/postgres:17.6-alpine3.22@sha256:747d5ed1fdeeb124b880fbe3d7c6557d2c4064ae41d6b6297d417882effce4be AS source

RUN set -eux; \
    root=/opt/dbtool-rootfs; \
    install -d "$root/usr/local/bin" "$root/etc/ssl"; \
    for binary in psql pg_dump pg_restore; do \
      cp -L "/usr/local/bin/$binary" "$root/usr/local/bin/$binary"; \
    done; \
    { \
      for binary in psql pg_dump pg_restore; do \
        ldd "/usr/local/bin/$binary"; \
      done; \
    } | awk '{ for (i = 1; i <= NF; i++) if ($i ~ /^\//) print $i }' | sort -u | \
      while read -r library; do \
        install -d "$root$(dirname "$library")"; \
        cp -L "$library" "$root$library"; \
      done; \
    cp -a /etc/ssl/openssl.cnf "$root/etc/ssl/openssl.cnf"; \
    "$root/usr/local/bin/psql" --version | grep -Fx 'psql (PostgreSQL) 17.6'; \
    "$root/usr/local/bin/pg_dump" --version | grep -Fx 'pg_dump (PostgreSQL) 17.6'; \
    "$root/usr/local/bin/pg_restore" --version | grep -Fx 'pg_restore (PostgreSQL) 17.6'

FROM scratch

LABEL org.opencontainers.image.source="https://github.com/muchenai2024-creator/muchen-journey-vnext" \
      org.opencontainers.image.title="Muchen Journey PostgreSQL 17.6 client" \
      org.opencontainers.image.description="Minimal client-only image for bounded WP-15 backup and isolated restore"

COPY --from=source /opt/dbtool-rootfs /

ENV PATH=/usr/local/bin

CMD ["psql", "--version"]
