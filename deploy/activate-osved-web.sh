#!/usr/bin/env bash
# One-time HTTPS activation on Hermes. Designed for an interactive operator.
# Never sends secrets to GitHub or prints environment file contents.
set -Eeuo pipefail

[[ "${EUID}" -eq 0 ]] || { echo "Run with sudo on Hermes" >&2; exit 1; }
DOMAIN=osved.tima.biz
HERMES_IPV4=31.76.77.87
APP=/opt/osved/app
SITE=/etc/nginx/sites-available/osved.tima.biz
ACTIVE=/etc/nginx/sites-enabled/osved.tima.biz

for binary in docker nginx certbot curl getent; do
  command -v "$binary" >/dev/null || { echo "Missing: $binary" >&2; exit 1; }
done
[[ -f "$APP/compose.yaml" && -f "$APP/.env" ]] || {
  echo "Expected deployed OSVED compose and private .env not found" >&2; exit 1;
}
cd "$APP"
echo "Checking internal OSVED portal..."
test "$(curl --fail --silent --max-time 5 http://127.0.0.1:18765/healthz)" = '{"status": "alive"}' ||
  test "$(curl --fail --silent --max-time 5 http://127.0.0.1:18765/healthz)" = '{"status":"alive"}' || {
    echo "Portal is not yet serving on localhost:18765. Do not enable nginx." >&2
    exit 1
  }

echo "Checking DNS for $DOMAIN..."
dns_addresses=$(getent ahostsv4 "$DOMAIN" | awk '{print $1}' | sort -u)
grep -Fxq "$HERMES_IPV4" <<< "$dns_addresses" || {
  echo "DNS A record must resolve $DOMAIN to Hermes $HERMES_IPV4" >&2
  exit 1
}
[[ ! -e "$SITE" && ! -L "$SITE" && ! -e "$ACTIVE" && ! -L "$ACTIVE" ]] || {
  echo "A nginx vhost already exists. Refusing to overwrite it." >&2
  exit 1
}

# No unknown root-executable source. Generate a minimal fixed reverse proxy only.
cat > "$SITE" <<'NGINX'
server {
    listen 80;
    server_name osved.tima.biz;

    location / {
        proxy_pass http://127.0.0.1:18765;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_connect_timeout 5s;
        proxy_read_timeout 30s;
        client_max_body_size 16k;
    }
}
NGINX
chmod 644 "$SITE"
ln -s "$SITE" "$ACTIVE"
if ! nginx -t; then
  rm -f "$ACTIVE" "$SITE"
  nginx -t || true
  echo "nginx validation failed; new vhost rolled back" >&2
  exit 1
fi
systemctl reload nginx

echo "Requesting HTTPS certificate through configured Certbot account..."
# This may ask for a Certbot account email if none has been configured previously.
certbot --nginx -d "$DOMAIN" --redirect
nginx -t
systemctl reload nginx
curl --fail --silent --show-error --max-time 10 "https://$DOMAIN/healthz" >/dev/null || {
  echo "HTTPS endpoint did not pass health verification. Bot WebApp stays disabled." >&2
  exit 1
}

# Enable Telegram Mini App launch only AFTER HTTPS passes.
if grep -q '^OSVED_WEB_URL=' "$APP/.env"; then
  sed -i 's|^OSVED_WEB_URL=.*|OSVED_WEB_URL=https://osved.tima.biz|' "$APP/.env"
else
  printf '\nOSVED_WEB_URL=https://osved.tima.biz\n' >> "$APP/.env"
fi
chmod 600 "$APP/.env"
docker compose up -d --no-deps --force-recreate newsfeed
echo "OSVED HTTPS configured. Telegram /start will show the WebApp launch button."
