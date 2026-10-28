# Módulo: `services` (`src/social_stats/services/`)

Servicios de coordinación del núcleo: agregación multiperfil (`ProfileAggregator`), planificación asíncrona de recolectores con *exponential backoff* (`CollectorScheduler`) y gestión de canales WebSocket.

---

## 1. Qué hace y qué NO hace

### 1.1. Qué hace
- `ProfileAggregator`: proyecta los estados únicos de `StateStore` hacia cada perfil definido en `profiles.json` / `profiles.yaml`, sumando automáticamente las métricas de múltiples cuentas de una misma red social (ej. varios canales de YouTube) y determinando el estado agregado por plataforma. Soporta el modo `public_only=True` (para `/ws/public`), donde filtra perfiles/cuentas con `public: false` o `disabled`, elimina `error_message` y `last_attempt_at`, y en `keycounter` redacta a `null` los contadores de hoy y 1h conservando únicamente los acumulados históricos (`pulsations_total` y `clicks_total`).
- `CollectorScheduler`: ejecuta bucles periódicos asíncronos por plataforma respetando el intervalo individual en minutos (`interval_minutes`) de cada cuenta (y agrupando en lotes las cuentas cuyo vencimiento coincide), con *jitter* aleatorio (`±5%`), *exponential backoff* hasta 3600s ante errores, enriquecimiento con `SnapshotRepository`, sanitización de errores (`sanitize_error_message`), notificación de cambios (`on_metric_update`, `on_status_change`) y tarea diaria de limpieza de SQLite (`_pruning_loop`).
- `WSManager`: gestiona suscripciones WebSocket separando suscriptores privados autenticados (`is_public=False`) y suscriptores públicos (`is_public=True`), aplicando límites de conexiones por IP y globales en el canal público, omitiendo `collector_status` hacia clientes públicos y evitando emitir `metric_update` en `/ws/public` cuando solo cambian las ventanas 1h/hoy de Keycounter.

### 1.2. Qué NO hace
- No implementa la lógica específica de extracción HTTP de cada red social (delegada en `collectors`).
- No define rutas HTTP/FastAPI directamente (delegadas en `api`).

---

## 2. Modelo de datos
- Produce instancias de `PlatformSummary`, `ProfileStats`, `GlobalStatsResponse`, `ProfilesCatalogResponse`, `CollectorHealthSummary`, `MetricUpdateData` y `CollectorStatusData`.

---

## 3. Flujos principales
1. `CollectorScheduler.run_collector_once(collector, accounts)` invoca `collector.collect_batch(accounts)`.
2. Si el lote o una cuenta individual falla, registra el fallo sanitizado en `StateStore` (pasando a `stale` si había datos previos) y emite `CollectorStatusData` (que `WSManager` envía solo a suscriptores privados).
3. Por cada cuenta exitosa, calcula $\Delta_{1h}$ y $\Delta_{24h}$ mediante `SnapshotRepository`, actualiza `StateStore` y, si `DiffEngine` detecta variaciones, construye y emite `MetricUpdateData` para cada perfil que referencie esa cuenta.

---

## 4. Puntos de entrada (Auth, permisos y límites)
- `ProfileAggregator.get_profile_stats(profile_id, platform_filter=None, public_only=False)`
- `ProfileAggregator.get_global_stats(profile_filter=None, platform_filter=None, public_only=False)`
- `ProfileAggregator.get_profiles_catalog(public_only=False)`
- `ProfileAggregator.is_account_public(profile_id, platform, account_key)`
- `ProfileAggregator.get_crypto_prices(symbol_filter=None)`
- `ProfileAggregator.get_keycounter_stats(account_filter=None)`
- `ProfileAggregator.get_collectors_health()`
- `CollectorScheduler.start()`, `stop()`, `run_collector_once()`
- `WSManager.can_accept_public(client_ip, max_connections, max_per_ip)`, `connect()`, `disconnect()`, `send_snapshot()`, `broadcast_update()`, `broadcast_collector_status()`, `broadcast_heartbeat()`, `start_heartbeat()`, `stop_heartbeat()`

---

## 5. Dependencias en ambos sentidos
- **Depende de:** `fastapi` (WebSocket), `social_stats.config`, `social_stats.models`, `social_stats.storage`, `social_stats.collectors.base`.
- **Consumido por:** `api`, `main`.

---

## 6. Configuración
| Variable / Parámetro | Tipo | Valor por defecto | Efecto / Comportamiento |
|---|---|---|---|
| `POLL_INTERVAL_<PLATFORM>` | `int` | `60`–`3600` | Intervalo base de recolección por plataforma |
| `SNAPSHOT_RETENTION_DAYS` | `int` | `30` | Días conservados por la tarea diaria de pruning |
| `WS_PUBLIC_MAX_PER_IP` | `int` | `5` | Límite de conexiones concurrentes por IP en `/ws/public` |
| `WS_PUBLIC_MAX_CONNECTIONS` | `int` | `150` | Límite global de conexiones concurrentes en `/ws/public` |

---

## 7. Trampas conocidas y consideraciones de diseño
- Precedencia determinista de estado en `compute_platform_status`: todas `disabled` $\rightarrow$ `disabled`; todas las activas `healthy` $\rightarrow$ `healthy`; todas las activas `error` $\rightarrow$ `error`; cualquier mezcla o cuenta en `stale` $\rightarrow$ `stale`.
- `WSManager` envía mensajes de forma concurrente con `asyncio.gather` aplicando un timeout de envío por socket (`DEFAULT_SEND_TIMEOUT_SECONDS = 5.0`) mediante `asyncio.wait_for`, desconectando automáticamente clientes lentos o colgados sin bloquear `CollectorScheduler` ni los heartbeats.
- Cuando una misma cuenta está referenciada en varios perfiles con distinto `label` o `handle`, `CollectorScheduler` proyecta los metadatos específicos de cada perfil al construir `MetricUpdateData`.

---

## 8. Tests que lo cubren
- [`tests/unit/test_aggregator.py`](../../tests/unit/test_aggregator.py)
- [`tests/integration/test_websockets.py`](../../tests/integration/test_websockets.py)
- Comando: `.venv/bin/pytest tests/unit/test_aggregator.py tests/integration/test_websockets.py`

---

## 9. Pendiente real
- Ninguno.

---
> Creado: 2026-10-28 · Última revisión: 2026-10-28
