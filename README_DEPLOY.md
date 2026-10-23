# Deploying ReviveShop

## Quick Start (Docker Compose)

1. Copy environment file:
```bash
cp .env.example .env
```

2. Generate TLS certificates:
```bash
mkdir -p certs
openssl req -x509 -newkey rsa:2048 -nodes -days 365 \
  -keyout certs/key.pem -out certs/cert.pem \
  -subj "/CN=reviveshop" \
  -addext "subjectAltName=DNS:localhost,IP:127.0.0.1"
```

3. Generate Theme Shop certificates:
```bash
cd theme-shop-revival && npm run gen-certs && cd ..
```

4. Start all services:
```bash
docker compose up -d
```

Services will be available on:
- Django (API/Portal): https://localhost:9000
- Flask (ECS/IAS/CAS): https://localhost:8000
- mitmproxy: http://localhost:8888
- Control Panel: http://localhost:5001
- Theme Shop: https://localhost:8443
- Caddy (reverse proxy): https://localhost:443

## 3DS Setup

For local network testing:
1. Set 3DS DNS to your server IP
2. Set 3DS proxy to `server-ip:8888` (or use the mitmproxy setup)
3. Install the CA certificate
4. Use the Theme Shop with NoSSL Luma patch

## Public Testing

For public access, deploy to your server with a domain and update DNS/Caddyfile accordingly.
