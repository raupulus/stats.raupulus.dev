# Módulo: `api` y `main` (`src/social_stats/api/`, `src/social_stats/main.py`)

Capa de exposición Read-Only con arquitectura de seguridad diferenciada en 3 canales: WebSocket público (`/ws/public`), WebSocket privado autenticado (`/ws/stats`, `/ws/profiles/{profile_id}`), API REST privada autenticada (`/api/v1/*`) y healthcheck interno de Docker (`GET /healthz`).

---

## 1. Qué hace y qué NO hace

### 1.1. Qué hace
- **Canal 1 — WebSocket Público (`WS /ws/public`, con `?profile={id}&platform={p}` opcional):**
  - Diseñado para la web pública (`stats.raupulus.dev` servida desde `public/`).
  - No exige token, pero aplica límites estándar estrictos antes de emitir `snapshot`: verificación de cabecera `Origin` (`WS_PUBLIC_ALLOWED_ORIGINS`), límite de conexiones simultáneas por IP (`WS_PUBLIC_MAX_PER_IP`) y global (`WS_PUBLIC_MAX_CONNECTIONS`), tamaño máximo de trama (`--ws-max-size 1024`) y cierre inmediato con código `1008` al recibir el **primer** mensaje entrante del cliente.
  - Expone únicamente perfiles y cuentas con `"public": true` y activas: todas las redes sociales públicas, criptomonedas (`BTC`, `ADA`) y en `keycounter` **exclusivamente los totales acumulados históricos** (`pulsations_total` y `clicks_total`), dejando `pulsations_today`, `pulsations_last_1h`, `clicks_today` y `clicks_last_1h` en `null`. Jamás expone `error_message`, `last_attempt_at` ni eventos `collector_status`.
- **Canal 2 — WebSocket Privado (`WS /ws/stats` y `WS /ws/profiles/{profile_id}`):**
  - Protegido obligatoriamente mediante `API_BEARER_TOKEN` (validado con `secrets.compare_digest` desde cabecera `Authorization: Bearer <token>`, `Sec-WebSocket-Protocol: bearer, <token>` o `?token=<token>`). Cierra con `1008` si no está autenticado.
  - Emite el 100% de las métricas sin recortes (incluyendo ventanas 1h y 24h/hoy de Keycounter, perfiles privados y eventos `collector_status`).
- **Canal 3 — API REST Privada (`/api/v1/*`):**
  - Protegida obligatoriamente con `Authorization: Bearer <API_BEARER_TOKEN>` (`401 Unauthorized` si falta o es inválido; *fail-closed* si `API_BEARER_TOKEN` está vacío).
  - En modo `production` (`APP_ENV=production`), oculta `/docs`, `/redoc` y `/openapi.json`.
  - Rutas bajo `/api/v1`:
    - `GET /api/v1/health`: estado de salud global, SQLite y resumen por colector.
    - `GET /api/v1/profiles`: catálogo completo de perfiles configurados.
    - `GET /api/v1/crypto`: cotizaciones spot y estadísticas 24h en USD y EUR (`?symbol=`).
    - `GET /api/v1/keycounter`: estadísticas completas de teclado y ratón (totales, hoy y última hora, `?account=`).
    - `GET /api/v1/stats`: estadísticas globales o filtradas por `?profile=` y `?platform=`.
    - `GET /api/v1/profiles/{profile_id}/stats`: estadísticas agregadas y desglosadas de un perfil (`?platform=`).
    - `GET /api/v1/profiles/{profile_id}/history`: serie temporal de snapshots históricos desde SQLite (`?window=1h|24h|7d|30d`).
- **Healthcheck Interno de Contenedor (`GET /healthz`):**
  - Restringido estrictamente a loopback local (`127.0.0.1`, `::1`, `localhost`) sin cabeceras de proxy inverso (`X-Forwarded-For`, `X-Real-IP`, `CF-Connecting-IP`, `Forwarded`). Devuelve `403 Forbidden` ante cualquier petición procedente de internet o proxy externo.
- **Middleware Read-Only y Cabeceras de Seguridad:**
  - Bloquea cualquier método HTTP distinto de `GET`, `HEAD` y `OPTIONS` devolviendo `405 Method Not Allowed`.
  - Inyecta `Content-Security-Policy`, `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: strict-origin-when-cross-origin`, `Permissions-Policy` y `Cross-Origin-Opener-Policy: same-origin`.
  - Monta automáticamente el directorio estático `public/` en `/` cuando está presente para despliegues integrados o locales.

### 1.2. Qué NO hace
- Jamás acepta mutaciones ni comandos de escritura desde los clientes.

---

## 2. Modelo de datos
- Utiliza los esquemas de `social_stats.models.api` (`HealthResponse`, `ProfilesCatalogResponse`, `GlobalStatsResponse`, `ProfileHistoryResponse`, `WSEventEnvelope`) y `ProfileStats`.

---

## 3. Flujos principales
1. Al iniciar FastAPI (`lifespan`), se conecta SQLite en modo WAL, se carga `profiles.json` (o `profiles.yaml`), se hidrata `StateStore` desde `account_latest_state`, y se inician `WSManager.start_heartbeat()` y `CollectorScheduler.start()`.
2. En peticiones REST `GET /api/v1/*`, la dependencia `require_private_api_token` verifica el token Bearer en tiempo constante antes de consultar `ProfileAggregator` en $O(1)$ o `SnapshotRepository.get_history()`.
3. En conexiones WebSocket (`/ws/public` o `/ws/stats`), tras superar las validaciones de origen/token y límites, `WSManager.connect()` envía el `snapshot` inicial adaptado al canal y registra la suscripción.

---

## 4. Puntos de entrada (Auth, permisos y límites)
- `create_app(...) -> FastAPI` y objeto `app` en `social_stats.main`.
- `src/social_stats/api/security.py`: `verify_bearer_token`, `require_private_api_token`, `extract_ws_bearer_token`, `is_local_loopback_request`, `is_allowed_public_ws_origin`.
- Función CLI `run()` invocada por el script `social-stats` (con `ws_max_size=1024`).

---

## 5. Dependencias en ambos sentidos
- **Depende de:** `fastapi`, `uvicorn`, `social_stats.config`, `social_stats.models`, `social_stats.storage`, `social_stats.services`, `social_stats.collectors`.
- **Consumido por:** Web pública (`public/`), clientes privados autenticados y servidor ASGI (`uvicorn`).

---

## 6. Configuración
| Variable / Parámetro | Tipo | Valor por defecto | Efecto / Comportamiento |
|---|---|---|---|
| `APP_ENV` | `str` | `"production"` | Si es `"production"`, desactiva `/docs`, `/redoc` y `/openapi.json` |
| `APP_HOST` | `str` | `"0.0.0.0"` | Host de escucha de Uvicorn |
| `APP_PORT` | `int` | `8000` | Puerto de escucha de Uvicorn |
| `API_BEARER_TOKEN` | `str` | `""` | Token Bearer requerido en `/api/v1/*`, `/ws/stats` y `/ws/profiles/{id}` |
| `CORS_ALLOWED_ORIGINS` | `str` | `"https://stats.raupulus.dev,http://localhost:8000"` | Orígenes permitidos en `CORSMiddleware` |
| `WS_PUBLIC_ALLOWED_ORIGINS` | `str` | `"https://stats.raupulus.dev,http://localhost:8000,http://127.0.0.1:8000"` | Cabeceras `Origin` permitidas en `/ws/public` |
| `WS_PUBLIC_MAX_PER_IP` | `int` | `5` | Máximo de conexiones simultáneas por IP en `/ws/public` |
| `WS_PUBLIC_MAX_CONNECTIONS` | `int` | `150` | Máximo global de conexiones simultáneas en `/ws/public` |

---

## 7. Trampas conocidas y consideraciones de diseño
- Si `config/profiles.json` no existe en entorno local de pruebas, `main.py` recurre automáticamente a `config/profiles.yaml` o a las plantillas `config/profiles.example.json` / `config/profiles.example.yaml`.
- Si `API_BEARER_TOKEN` no está configurado (cadena vacía), todos los endpoints privados (`/api/v1/*`, `/ws/stats`, `/ws/profiles/{id}`) fallan en modo cerrado (*fail-closed*) rechazando cualquier petición.

---

## 8. Tests que lo cubren
- [`tests/integration/test_rest_api.py`](../../tests/integration/test_rest_api.py)
- [`tests/integration/test_websockets.py`](../../tests/integration/test_websockets.py)
- Comando: `.venv/bin/pytest tests/integration/`

---

## 9. Pendiente real
- Ninguno.

---
> Creado: 2026-10-28 · Última revisión: 2026-10-28
