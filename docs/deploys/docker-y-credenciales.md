# Guía de Despliegue en Docker, VPN y Obtención de Credenciales Permanentes

Guía operativa para desplegar el contenedor en un servidor privado accesible por VPN y configurar las credenciales sin caducidad semanal.

---

## 1. Despliegue con Docker Compose

1. Copiar las plantillas de configuración y asignar permisos al volumen de datos (`UID 10001` del usuario `appuser` dentro del contenedor):
   ```bash
   cp .env.example .env
   cp config/profiles.example.json config/profiles.json
   mkdir -p data
   sudo chown -R 10001:10001 data
   chmod 750 data
   ```
2. Editar `config/profiles.json` definiendo los activos globales de cripto en la clave raíz `"crypto"` (`BTC`, `ADA`, etc.) y tus perfiles en `"profiles"` (ej. `raupulus`, `proyecto_secundario`), indicando `"enable": true` (o `false`) para activar/desactivar perfiles o cuentas individuales, `"public": true` (o `false`) para controlar qué perfiles/cuentas se muestran en la web pública (`/ws/public`), e `"interval_minutes"` para ajustar el tiempo de consulta en minutos de cada cuenta.
3. En `.env`, configurar `BIND_IP` (`127.0.0.1` tras proxy inverso o IP privada de VPN), generar un token seguro para `API_BEARER_TOKEN` (requerido para `/api/v1/*` y `/ws/stats`), definir `WS_PUBLIC_ALLOWED_ORIGINS=https://stats.raupulus.dev` y añadir `KEYCOUNTER_API_TOKEN` y las claves necesarias.
4. Levantar el servicio:
   ```bash
   docker compose up --build -d
   ```
5. Verificar el healthcheck local del contenedor o consultar la API privada con token:
   ```bash
   curl http://127.0.0.1:8000/healthz
   curl -H "Authorization: Bearer <API_BEARER_TOKEN>" http://127.0.0.1:8000/api/v1/health
   ```

---

## 2. Seguridad del Contenedor y Separación de Canales
- **Contexto de build limpio (`.dockerignore`):** Excluye `.env`, `config/profiles.json`, `data/`, `.git/`, `.venv/`, `tests/` y `docs/` para evitar filtraciones accidentales en las capas de la imagen.
- **Usuario sin privilegios y sin capabilities:** El proceso corre bajo `appuser` (`UID 10001`), con `no-new-privileges:true`, `cap_drop: [ALL]` y `stop_grace_period: 15s`.
- **Filesystem raíz de solo lectura (`read_only: true`):** Solo `/app/data` (volumen persistente SQLite WAL) y `/tmp` (`tmpfs: size=64M,mode=1777`) permiten escritura; `./config` y `./public` se montan en modo `:ro`.
- **Consumo 100% Read-Only:** Cualquier método HTTP distinto de `GET`, `HEAD` u `OPTIONS` recibe `405 Method Not Allowed`.
- **Healthcheck exclusivo de localhost (`GET /healthz`):** Solo responde a peticiones directas desde loopback (`127.0.0.1` / `::1`) sin cabeceras de proxy inverso; rechaza peticiones externas con `403 Forbidden`.
- **Cero credenciales en URLs:** Las claves de YouTube (`X-Goog-Api-Key`), Instagram (`Authorization: Bearer`) y Keycounter (`Authorization: Bearer`) viajan exclusivamente por cabeceras HTTP y los errores se sanitizan antes de guardarse en memoria o SQLite.

---

## 3. Obtención de Credenciales Permanentes (Zero Manual Relogin)

### 3.1. YouTube (`YOUTUBE_API_KEY` — Nunca caduca)
1. Acceder a [Google Cloud Console](https://console.cloud.google.com/).
2. Habilitar **YouTube Data API v3** en *APIs & Services > Library*.
3. Crear una clave en *Credentials > Create Credentials > API Key* y restringirla a *YouTube Data API v3*.
4. Asignar el valor a `YOUTUBE_API_KEY` en `.env`.

### 3.2. Bluesky, Mastodon y Telegram (Sin credenciales)
- Funcionan directamente contra sus APIs públicas abiertas (`https://public.api.bsky.app`, `https://{instance}/api/v1`) y la vista previa pública de canales (`https://t.me/s/{handle}`).

### 3.3. Instagram y Facebook (`IG_MAIN_ACCESS_TOKEN` / `FB_MAIN_ACCESS_TOKEN` — System User Token permanente o modo Web sin token)
- **Con System User Token (Recomendado):** En Meta Business Suite (*Usuarios > Usuarios del sistema*), generar un token con permisos de lectura y caducidad **"Nunca" (Never)** y definir `IG_MAIN_USER_ID` / `IG_MAIN_ACCESS_TOKEN` o `FB_MAIN_PAGE_ID` / `FB_MAIN_ACCESS_TOKEN` en `.env`.
- **Sin token:** Si se dejan vacíos, `InstagramCollector` y `FacebookCollector` emplean automáticamente el fallback de perfil web y metadatos OpenGraph con huella TLS (`curl_cffi`).

### 3.4. Twitter/X, TikTok y Twitch (Sin credenciales por defecto)
- Funcionan sin claves en `.env` mediante la Syndication API / SSR fallback de Twitter, el extractor de hidratación SSR de TikTok y el endpoint público GraphQL de Twitch (`https://gql.twitch.tv/gql`).
- Opcionalmente admiten `TWITTER_AUTH_TOKEN_COOKIE`/`TWITTER_CT0_COOKIE`, credenciales de TikTok Display API (`TIKTOK_CLIENT_KEY`/`TIKTOK_CLIENT_SECRET`) o credenciales de Twitch Helix (`TWITCH_CLIENT_ID`/`TWITCH_CLIENT_SECRET`).

### 3.5. GitHub y GitLab (Sin credenciales por defecto o Token Read-Only opcional)
- Funcionan de forma pública sin credenciales (`api.github.com/users/{handle}` y `gitlab.com/api/v4` + XHR `followers.json`).
- Opcionalmente admiten `GITHUB_TOKEN` (eleva la cuota de 60 a 5.000 peticiones/hora) y `GITLAB_TOKEN` (`read_api`).

### 3.6. Keycounter (`KEYCOUNTER_API_URL` y `KEYCOUNTER_API_TOKEN`)
- Asignar en `.env` la URL del servidor de telemetría en `KEYCOUNTER_API_URL` y el token Bearer en `KEYCOUNTER_API_TOKEN`.
- El límite de tasa es de 60 peticiones/minuto por token; se recomienda `"interval_minutes": 1` en `config/profiles.json`.

---

## 4. Consumo desde Clientes (3 Canales Diferenciados)

### 4.1. Canal 1: WebSocket Público (`WS /ws/public` — Sin token, para `stats.raupulus.dev`)
- URL: `wss://stats.raupulus.dev/ws/public` (admite `?profile=raupulus&platform=youtube`).
- Protegido por validación de `Origin` (`WS_PUBLIC_ALLOWED_ORIGINS`), límite de conexiones por IP (`WS_PUBLIC_MAX_PER_IP`), límite global (`WS_PUBLIC_MAX_CONNECTIONS`) y cierre inmediato (`1008`) si el cliente envía cualquier mensaje.
- Expone únicamente perfiles y cuentas con `"public": true`, todas las redes sociales públicas, criptomonedas globales (`BTC`, `ADA`) y en `keycounter` **solo los totales acumulados históricos** (`pulsations_total` y `clicks_total`).

### 4.2. Canal 2: WebSocket Privado (`WS /ws/stats` y `WS /ws/profiles/{profile_id}` — Con `API_BEARER_TOKEN`)
- Requiere autenticación mediante cabecera `Authorization: Bearer <API_BEARER_TOKEN>`, subprotocolo `Sec-WebSocket-Protocol: bearer, <API_BEARER_TOKEN>` o parámetro `?token=<API_BEARER_TOKEN>`.
- Emite el 100% de los datos sin recortes (incluyendo ventanas de 1h y hoy de Keycounter y eventos `collector_status`).

### 4.3. Canal 3: API REST Privada (`GET /api/v1/*` — Con `Authorization: Bearer <API_BEARER_TOKEN>`)
- `GET /api/v1/health` — Estado de salud del servidor, SQLite y colectores.
- `GET /api/v1/profiles` — Catálogo de perfiles configurados.
- `GET /api/v1/crypto` — Precios spot globales y estadísticas 24h de criptomonedas (`BTC`, `ADA`, etc.) en USD y EUR.
- `GET /api/v1/keycounter` — Estadísticas completas de pulsaciones de teclas y clics de ratón (totales, hoy y última hora).
- `GET /api/v1/stats` — Estadísticas de todos los perfiles (`?profile=raupulus&platform=youtube`).
- `GET /api/v1/profiles/{profile_id}/stats` — Estadísticas agregadas y por cuenta de un perfil.
- `GET /api/v1/profiles/{profile_id}/history?window=24h` — Serie temporal histórica (`1h`, `24h`, `7d`, `30d`).

---
> Creado: 2026-10-28 · Última revisión: 2026-10-29
