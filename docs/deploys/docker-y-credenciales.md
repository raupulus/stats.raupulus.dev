# Guía de Despliegue en Docker, VPN y Obtención de Credenciales Permanentes

Guía operativa para desplegar el contenedor en un servidor privado accesible por VPN y configurar las credenciales sin caducidad semanal.

---

## 1. Despliegue con Docker Compose

1. Copiar las plantillas de configuración:
   ```bash
   cp .env.example .env
   cp config/profiles.example.json config/profiles.json
   mkdir -p data
   ```
2. Editar `config/profiles.json` definiendo tus perfiles (ej. `raupulus`, `proyecto_secundario`), indicando `"enable": true` (o `false`) para activar/desactivar perfiles o cuentas individuales, y `"interval_minutes"` para ajustar el tiempo de consulta en minutos de cada cuenta.
3. En `.env`, configurar `BIND_IP` con la dirección IP privada de la interfaz VPN del servidor (ej. `100.x.y.z` en Tailscale o `10.8.0.1` en WireGuard) o `127.0.0.1` para acceso local, además de `KEYCOUNTER_API_TOKEN` y las claves necesarias.
4. Levantar el servicio:
   ```bash
   docker compose up --build -d
   ```
5. Verificar el estado de salud:
   ```bash
   curl http://127.0.0.1:8000/api/v1/health
   ```

---

## 2. Seguridad del Contenedor
- **Usuario sin privilegios:** El proceso corre bajo `appuser` (`UID 10001`).
- **Filesystem raíz de solo lectura (`read_only: true`):** Solo `/app/data` (volumen persistente SQLite WAL) y `/tmp` (`tmpfs`) permiten escritura.
- **Consumo 100% Read-Only:** Cualquier método HTTP distinto de `GET`, `HEAD` u `OPTIONS` recibe `405 Method Not Allowed`.

---

## 3. Obtención de Credenciales Permanentes (Zero Manual Relogin)

### 3.1. YouTube (`YOUTUBE_API_KEY` — Nunca caduca)
1. Acceder a [Google Cloud Console](https://console.cloud.google.com/).
2. Habilitar **YouTube Data API v3** en *APIs & Services > Library*.
3. Crear una clave en *Credentials > Create Credentials > API Key* y restringirla a *YouTube Data API v3*.
4. Asignar el valor a `YOUTUBE_API_KEY` en `.env`.

### 3.2. Bluesky y Mastodon (Sin credenciales)
- Funcionan directamente contra sus APIs públicas abiertas (`https://public.api.bsky.app` y `https://{instance}/api/v1`).

### 3.3. Instagram (`IG_MAIN_ACCESS_TOKEN` — System User Token permanente o modo Web sin token)
- **Con System User Token (Recomendado):** En Meta Business Suite (*Usuarios > Usuarios del sistema*), generar un token con permisos `instagram_basic` y caducidad **"Nunca" (Never)** y definir `IG_MAIN_USER_ID` e `IG_MAIN_ACCESS_TOKEN` en `.env`.
- **Sin token:** Si se dejan vacíos, `InstagramCollector` emplea automáticamente el fallback de perfil web con huella TLS (`curl_cffi`).

### 3.4. Twitter/X y TikTok (Sin credenciales por defecto)
- Funcionan sin claves en `.env` mediante la Syndication API de Twitter y el extractor de hidratación SSR de TikTok.
- Opcionalmente admiten `TWITTER_AUTH_TOKEN_COOKIE`/`TWITTER_CT0_COOKIE` o credenciales de TikTok Display API (`TIKTOK_CLIENT_KEY`/`TIKTOK_CLIENT_SECRET`).

### 3.5. Keycounter (`KEYCOUNTER_API_TOKEN`)
- Asignar en `.env` el token Bearer generado para `GET https://api.raupulus.dev/api/v2/keycounter/stats` en `KEYCOUNTER_API_TOKEN`.
- El límite de tasa es de 60 peticiones/minuto por token; se recomienda `"interval_minutes": 1` en `config/profiles.json`.

---

## 4. Consumo desde Clientes (REST y WebSockets)

### 4.1. Consultas REST (`GET`)
- `GET /api/v1/health` — Estado de salud del servidor, SQLite y colectores.
- `GET /api/v1/profiles` — Catálogo de perfiles configurados.
- `GET /api/v1/crypto` — Precios spot y estadísticas 24h de criptomonedas (`BTC`, `ADA`, etc.) en USD y EUR.
- `GET /api/v1/keycounter` — Estadísticas de pulsaciones de teclas y clics de ratón (totales, hoy y última hora).
- `GET /api/v1/stats` — Estadísticas de todos los perfiles (`?profile=raupulus&platform=youtube`).
- `GET /api/v1/profiles/{profile_id}/stats` — Estadísticas agregadas y por cuenta de un perfil.
- `GET /api/v1/profiles/{profile_id}/history?window=24h` — Serie temporal histórica (`1h`, `24h`, `7d`, `30d`).

### 4.2. Suscripciones WebSocket (Read-Only)
- Canal Global (todos los perfiles): `ws://<host>:8000/ws/stats`
- Canal Filtrado por Perfil: `ws://<host>:8000/ws/stats?profile=raupulus` o `ws://<host>:8000/ws/profiles/raupulus`
- Filtro adicional por plataforma: `?platform=youtube`
- Al conectar, el servidor emite inmediatamente un evento `snapshot` con el estado completo en caché, seguido de eventos `metric_update` cuando cambian las métricas, `collector_status` si varía la salud de un proveedor y `heartbeat` cada 30 segundos.

---
> Creado: 2026-10-28 · Última revisión: 2026-10-28
