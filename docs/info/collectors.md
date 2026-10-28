# Módulo: `collectors` (`src/social_stats/collectors/`)

Interfaz común (`BaseCollector`) y proveedores desacoplados de recolección asíncrona de métricas por red social.

---

## 1. Qué hace y qué NO hace

### 1.1. Qué hace
- Define el contrato abstracto `BaseCollector` (`collect_batch(accounts) -> dict[str, AccountMetrics]`).
- Provee utilidades para registrar errores por cuenta (`record_account_error`) y cuentas deshabilitadas (`record_account_disabled`) sin abortar la recolección del resto de cuentas del lote.
- Implementa los colectores de Nivel 1:
  - `YouTubeCollector` (`youtube.py`): consulta batch multicanal (hasta 50 canales por llamada) y resolución cacheada de `@handle` a `UC...`.
  - `BlueskyCollector` (`bluesky.py`): consulta batch de perfiles (`getProfiles`) y último post original (`getAuthorFeed` descartando reposts).
  - `MastodonCollector` (`mastodon.py`): consulta pública multi-instancia (`accounts/lookup` + `statuses`) con aislamiento de errores por instancia.

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
3. Devuelve las métricas normalizadas por cada `account_key` exitoso y anota en `last_errors` cualquier fallo individual.

---

## 4. Puntos de entrada (Auth, permisos y límites)
- `BaseCollector.collect_batch(accounts: list[AccountConfig]) -> dict[str, AccountMetrics]`
- `YouTubeCollector(api_key, snapshot_repo=..., http_client=...)`
- `BlueskyCollector(snapshot_repo=..., http_client=...)`
- `MastodonCollector(snapshot_repo=..., http_client=...)`

---

## 5. Dependencias en ambos sentidos
- **Depende de:** `httpx`, `social_stats.config`, `social_stats.models`, `social_stats.storage`.
- **Consumido por:** `services.scheduler`, `main`.

---

## 6. Configuración
| Variable / Parámetro | Tipo | Valor por defecto | Efecto / Comportamiento |
|---|---|---|---|
| `YOUTUBE_API_KEY` | `str` | `""` | API Key de Google Cloud para `YouTubeCollector` |
| `POLL_INTERVAL_YOUTUBE` | `int` | `300` | Intervalo de recolección de YouTube (segundos) |
| `POLL_INTERVAL_BLUESKY` | `int` | `120` | Intervalo de recolección de Bluesky (segundos) |
| `POLL_INTERVAL_MASTODON` | `int` | `180` | Intervalo de recolección de Mastodon (segundos) |

---

## 7. Trampas conocidas y consideraciones de diseño
- Ninguna llamada HTTP supera los 15 segundos (`DEFAULT_HTTP_TIMEOUT = httpx.Timeout(15.0, connect=5.0)`).
- En `YouTubeCollector`, cuando `hiddenSubscriberCount` es `true`, `followers_total` se reporta como `None`.
- En `BlueskyCollector`, `getAuthorFeed` con `filter=posts_no_replies` puede seguir incluyendo reposts en los que `reason` no es `None`; el colector los filtra explícitamente.

---

## 8. Tests que lo cubren
- [`tests/unit/collectors/test_youtube.py`](../../tests/unit/collectors/test_youtube.py)
- [`tests/unit/collectors/test_bluesky.py`](../../tests/unit/collectors/test_bluesky.py)
- [`tests/unit/collectors/test_mastodon.py`](../../tests/unit/collectors/test_mastodon.py)
- Comando: `.venv/bin/pytest tests/unit/collectors/`

---

## 9. Pendiente real
- Colectores de Nivel 2 (`TwitterCollector`, `InstagramCollector`, `TikTokCollector`) en Fase 4 y Nivel 3 (`LinkedInCollector`) en Fase 5.

---
> Creado: 2026-10-28 · Última revisión: 2026-10-28
