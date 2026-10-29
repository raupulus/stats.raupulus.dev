# Módulo: `collectors` (`src/social_stats/collectors/`)

Interfaz común (`BaseCollector`) y proveedores desacoplados de recolección asíncrona de métricas para las 12 plataformas sociales/forjas soportadas, criptomonedas (`CryptoCollector`) y pulsaciones de teclado/clics (`KeycounterCollector`) — 14 colectores en total.

---

## 1. Qué hace y qué NO hace

### 1.1. Qué hace
- Define el contrato abstracto `BaseCollector` (`collect_batch(accounts) -> dict[str, AccountMetrics]`) y el filtro de seguridad `sanitize_error_message()` que redacta automáticamente cualquier URL (`https?://...`), query string, token `Bearer` o credencial en mensajes de error antes de registrarlos en memoria, logs o base de datos.
- Provee utilidades para registrar errores por cuenta (`record_account_error`) y cuentas deshabilitadas (`record_account_disabled`) sin abortar la recolección del resto de cuentas del lote.
- Implementa los colectores de Nivel 1 (100% abiertos o con API Key / Bearer Token permanente enviado exclusivamente en cabeceras HTTP, nunca en URL):
  - `YouTubeCollector` (`youtube.py`): consulta batch multicanal (hasta 50 canales por llamada) y resolución cacheada de `@handle` a `UC...`, enviando la clave en la cabecera `X-Goog-Api-Key`.
  - `BlueskyCollector` (`bluesky.py`): consulta batch de perfiles (`getProfiles`) y último post original (`getAuthorFeed` descartando reposts).
  - `MastodonCollector` (`mastodon.py`): consulta pública multi-instancia (`accounts/lookup` + `statuses`) con aislamiento de errores por instancia.
  - `GitHubCollector` (`github.py`): consulta de seguidores, repositorios públicos (`public_repos`) y suma paginada de estrellas (`stars_total`) y forks (`forks_total`), con soporte opcional de token de solo lectura en cabecera `Authorization: Bearer <TOKEN>`.
  - `GitLabCollector` (`gitlab.py`): consulta multi-instancia (`gitlab.com` o autoalojada) combinando API REST v4 (`/api/v4/users`, `/api/v4/users/:id/projects`, cabecera `PRIVATE-TOKEN` opcional) con fallback público XHR (`/users/:handle/followers.json`) cuando `/api/v4/users/:id` requiere autenticación.
  - `TelegramCollector` (`telegram.py`): extracción pasiva desde `https://t.me/s/{handle}` (suscriptores, secuencia de mensajes y vistas del último post) sin Bot API ni tokens en URLs.
  - `CryptoCollector` (`crypto.py`): consulta batch de cotizaciones spot y estadísticas 24h en dólares (`USDT`) y euros (`EUR`) mediante Binance Public Market API (`/api/v3/ticker/24hr`) sin tokens.
  - `KeycounterCollector` (`keycounter.py`): consulta de pulsaciones de teclas y clics de ratón (totales históricos, hoy y última hora) contra el endpoint configurado en `KEYCOUNTER_API_URL` (`https://api.example.com/api/v2/keycounter/stats` por defecto) con autenticación `Authorization: Bearer <TOKEN>`.
- Implementa los colectores de Nivel 2 (arquitectura dual con fallback automático):
  - `TwitterCollector` (`twitter.py`): Nivel A Syndication API (`followbutton/info.json` + `timeline-profile`), Nivel B GraphQL con cookies Read-Only opcionales, y fallback automático de contingencia a SSR HTML con `curl_cffi` cuando Syndication experimenta `HTTP 429`.
  - `InstagramCollector` (`instagram.py`): Nivel A Meta Graph API con System User Token permanente en cabecera `Authorization: Bearer <TOKEN>`, Nivel B fallback `web_profile_info` con `curl_cffi`, y fallback automático a OpenGraph HTML cuando `web_profile_info` responde `401`.
  - `TikTokCollector` (`tiktok.py`): extracción SSR desde `<script id="__UNIVERSAL_DATA_FOR_REHYDRATION__">` con `curl_cffi` y soporte opcional para TikTok Display API v2 con rotación automática de `refresh_token` en SQLite.
  - `TwitchCollector` (`twitch.py`): Nivel A Twitch Helix API oficial (App Access Token `client_credentials` auto-renovado en cuerpo `POST`) y Nivel B fallback público Twitch GQL (`https://gql.twitch.tv/gql`), reportando seguidores, VODs, `is_live` y `live_viewers`.
  - `FacebookCollector` (`facebook.py`): Nivel A Meta Graph API v21.0 (`followers_count`, `fan_count` con cabecera `Authorization: Bearer`) y Nivel B fallback público OpenGraph HTML bilingüe con `curl_cffi`.
- Implementa el colector de Nivel 3 (aislado y opcional):
  - `LinkedInCollector` (`linkedin.py`): modos `organization` (API oficial) y `personal` (Voyager API con cookie `li_at`), reportando `status: "disabled"` si no se configuran credenciales.

### 1.2. Qué NO hace
- No modifica directamente el `StateStore` ni envía mensajes por WebSockets (eso lo orquesta `CollectorScheduler`).

---

## 2. Modelo de datos
- Entrada: `list[AccountConfig]` (cuentas activas deduplicadas por plataforma).
- Salida: `dict[str, AccountMetrics]` indexado por `account_key`.

---

## 3. Flujos principales
1. `CollectorScheduler` llama a `collector.reset_cycle_tracking()` y `await collector.collect_batch(accounts)`.
2. El colector consulta la API o fuente externa con timeout máximo de 15 segundos (`DEFAULT_HTTP_TIMEOUT`).
3. Devuelve las métricas normalizadas por cada `account_key` exitoso y anota en `last_errors` o `disabled_accounts` cualquier incidencia individual.

---

## 4. Puntos de entrada (Auth, permisos y límites)
- `BaseCollector.collect_batch(accounts: list[AccountConfig]) -> dict[str, AccountMetrics]`
- `YouTubeCollector`, `BlueskyCollector`, `MastodonCollector`, `TwitterCollector`, `InstagramCollector`, `TikTokCollector`, `LinkedInCollector`, `GitHubCollector`, `GitLabCollector`, `TelegramCollector`, `TwitchCollector`, `FacebookCollector`, `CryptoCollector`, `KeycounterCollector`.

---

## 5. Dependencias en ambos sentidos
- **Depende de:** `httpx`, `curl_cffi`, `social_stats.config`, `social_stats.models`, `social_stats.storage`.
- **Consumido por:** `services.scheduler`, `main`.

---

## 6. Configuración
| Variable / Parámetro | Tipo | Valor por defecto | Efecto / Comportamiento |
|---|---|---|---|
| `YOUTUBE_API_KEY` | `str` | `""` | API Key de Google Cloud para `YouTubeCollector` |
| `IG_MAIN_USER_ID` / `IG_MAIN_ACCESS_TOKEN` | `str` | `""` | Credenciales permanentes Meta Graph API para `InstagramCollector` |
| `FB_MAIN_PAGE_ID` / `FB_MAIN_ACCESS_TOKEN` | `str` | `""` | Credenciales opcionales Meta Graph API para `FacebookCollector` |
| `TWITTER_AUTH_TOKEN_COOKIE` / `TWITTER_CT0_COOKIE` | `str` | `""` | Cookies opcionales Read-Only para Nivel B de `TwitterCollector` |
| `TIKTOK_CLIENT_KEY` / `TIKTOK_CLIENT_SECRET` | `str` | `""` | Credenciales opcionales Display API v2 para `TikTokCollector` |
| `LINKEDIN_ACCESS_TOKEN` / `LINKEDIN_LI_AT_COOKIE` | `str` | `""` | Credenciales opcionales para `LinkedInCollector` |
| `GITHUB_TOKEN` | `str` | `""` | Token opcional Read-Only (`5.000 req/h`) para `GitHubCollector` |
| `GITLAB_TOKEN` | `str` | `""` | Token opcional `read_api` para `GitLabCollector` |
| `TWITCH_CLIENT_ID` / `TWITCH_CLIENT_SECRET` | `str` | `""` | Credenciales opcionales Helix OAuth2 App Token para `TwitchCollector` |
| `KEYCOUNTER_API_TOKEN` | `str` | `""` | Token Bearer para `KeycounterCollector` |
| `KEYCOUNTER_API_URL` | `str` | `"https://api.example.com/api/v2/keycounter/stats"` | Endpoint de `KeycounterCollector` |

---

## 7. Trampas conocidas y consideraciones de diseño
- Ninguna llamada HTTP supera los 15 segundos (`DEFAULT_HTTP_TIMEOUT = httpx.Timeout(15.0, connect=5.0)`).
- `InstagramCollector`, `FacebookCollector` (en fallback Nivel B) y `TikTokCollector` (en extracción SSR) utilizan `curl_cffi` con `impersonate="chrome124"` cuando `use_curl_cffi=True` (habilitado por defecto en `build_default_collectors` de `main.py`) y admiten inyección de `httpx.AsyncClient` en tests deterministas.
- En `gitlab.com`, el endpoint `/api/v4/users/:id` devuelve `HTTP 403` sin cabecera `PRIVATE-TOKEN`; `GitLabCollector` conmuta automáticamente al endpoint XHR público `/users/:handle/followers.json`.
- `TelegramCollector` prescinde deliberadamente de la Bot API oficial para no incluir jamás tokens secretos en rutas URL (`/bot<TOKEN>/...`).
- `BaseCollector.reset_cycle_tracking(now_ts=...)` propaga el instante de evaluación de `CollectorScheduler` hacia `enrich_with_snapshots()` y registra las cuentas enriquecidas en `enriched_accounts` para evitar inserciones duplicadas de snapshots en un mismo ciclo.
- En `TwitterCollector`, los tweets del timeline se ordenan por `snowflake id` numérico descendente para evitar que un tweet fijado antiguo sea tomado como el último post.
- En `LinkedInCollector`, la ausencia de credenciales marca la cuenta como `disabled` en lugar de `error` para no degradar el estado de salud global si no se utiliza LinkedIn.

---

## 8. Tests que lo cubren
- [`tests/unit/collectors/test_youtube.py`](../../tests/unit/collectors/test_youtube.py)
- [`tests/unit/collectors/test_bluesky.py`](../../tests/unit/collectors/test_bluesky.py)
- [`tests/unit/collectors/test_mastodon.py`](../../tests/unit/collectors/test_mastodon.py)
- [`tests/unit/collectors/test_twitter.py`](../../tests/unit/collectors/test_twitter.py)
- [`tests/unit/collectors/test_instagram.py`](../../tests/unit/collectors/test_instagram.py)
- [`tests/unit/collectors/test_tiktok.py`](../../tests/unit/collectors/test_tiktok.py)
- [`tests/unit/collectors/test_linkedin.py`](../../tests/unit/collectors/test_linkedin.py)
- [`tests/unit/collectors/test_github.py`](../../tests/unit/collectors/test_github.py)
- [`tests/unit/collectors/test_gitlab.py`](../../tests/unit/collectors/test_gitlab.py)
- [`tests/unit/collectors/test_telegram.py`](../../tests/unit/collectors/test_telegram.py)
- [`tests/unit/collectors/test_twitch.py`](../../tests/unit/collectors/test_twitch.py)
- [`tests/unit/collectors/test_facebook.py`](../../tests/unit/collectors/test_facebook.py)
- [`tests/unit/collectors/test_crypto.py`](../../tests/unit/collectors/test_crypto.py)
- [`tests/unit/collectors/test_keycounter.py`](../../tests/unit/collectors/test_keycounter.py)
- Comando: `.venv/bin/pytest tests/unit/collectors/`

---

## 9. Pendiente real
- Ninguno. Los 14 colectores están implementados y cubiertos por tests unitarios.

---
> Creado: 2026-10-28 · Última revisión: 2026-10-29
