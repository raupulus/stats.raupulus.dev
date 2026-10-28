# Módulo: `models` (`src/social_stats/models/`)

Esquemas y modelos de datos tipados con Pydantic v2 para métricas internas, estados de cuentas, resúmenes agregados por perfil, respuestas REST y sobres de eventos WebSocket.

---

## 1. Qué hace y qué NO hace

### 1.1. Qué hace
- Define las enumeraciones del dominio (`Platform`, `CollectorStatus`, `WSEventType`).
- Define los modelos de métricas y estados de cuentas (`LatestPostMetrics`, `AccountMetrics`, `AccountState`, `PlatformSummary`, `ProfileStats`).
- Define todos los contratos de salida de la API REST y WebSockets (`GlobalStatsResponse`, `ProfilesCatalogResponse`, `ProfileHistoryResponse`, `CryptoAssetPrice`, `CryptoPricesResponse`, `HealthResponse`, `WSEventEnvelope`, `MetricUpdateData`, `CollectorStatusData`, `HeartbeatData`).

### 1.2. Qué NO hace
- No contiene lógica de acceso a base de datos ni de red.
- No realiza cálculos de agregación ni de diferencias (delegados en `ProfileAggregator` y `DiffEngine`).

---

## 2. Modelo de datos
- `Platform`: `youtube`, `twitter`, `instagram`, `bluesky`, `mastodon`, `tiktok`, `linkedin`, `crypto`, `keycounter`.
- `CollectorStatus`: `healthy`, `stale`, `error`, `disabled`.
- `WSEventType`: `snapshot`, `metric_update`, `collector_status`, `heartbeat`.
- `AccountMetrics`: `followers_total`, `followers_last_24h`, `posts_total`, `views_total`, `views_last_24h`, `views_last_1h`, `window_1h_complete`, `window_24h_complete`, `latest_post`, campos de cotización cripto (`price_usd`, `price_eur`, `price_change_24h_usd`, `price_change_24h_pct`, `price_change_24h_eur`, `price_change_24h_eur_pct`, `high_24h_usd`, `low_24h_usd`, `high_24h_eur`, `low_24h_eur`) y campos de actividad de teclado/ratón (`pulsations_total`, `pulsations_today`, `pulsations_last_1h`, `clicks_total`, `clicks_today`, `clicks_last_1h`).
- `CryptoAssetPrice` y `CryptoPricesResponse`: Esquemas dedicados para `GET /api/v1/crypto`.
- `KeycounterAccountStats` y `KeycounterStatsResponse`: Esquemas dedicados para `GET /api/v1/keycounter`.
- `PlatformSummary`: Resumen agregado por red social o plataforma dentro de un perfil con desglose en `accounts`.
- `WSEventEnvelope`: Sobre uniforme `{event, timestamp, scope, data}` para todos los eventos WebSocket.

---

## 3. Flujos principales
1. Los colectores producen instancias de `AccountMetrics`.
2. `SnapshotRepository` enriquece `AccountMetrics` con $\Delta_{1h}$ y $\Delta_{24h}$.
3. `StateStore` envuelve las métricas en `AccountState`.
4. `ProfileAggregator` agrupa los `AccountState` en `PlatformSummary` y `ProfileStats`.
5. Los endpoints REST y WebSocket serializan `GlobalStatsResponse`, `ProfileStats` y `WSEventEnvelope` a JSON.

---

## 4. Puntos de entrada (Auth, permisos y límites)
- Modelos exportados en `social_stats.models`. Sin autenticación ni efectos laterales.

---

## 5. Dependencias en ambos sentidos
- **Depende de:** `pydantic`, librería estándar (`enum`, `datetime`, `typing`).
- **Consumido por:** `storage`, `services`, `collectors`, `api`.

---

## 6. Configuración
No requiere variables de entorno propias.

---

## 7. Trampas conocidas y consideraciones de diseño
- En `MetricChange`, el campo `previous` es `int | None` para representar limpiamente la primera lectura cuando el valor previo era `None`.
- Los campos acumulados no soportados por ciertas plataformas (ej. `views_total` en Bluesky/Mastodon/Twitter) permanecen en `None` para distinguirlos de un contador real en `0`.

---

## 8. Tests que lo cubren
- [`tests/unit/test_snapshot_deltas.py`](../../tests/unit/test_snapshot_deltas.py)
- [`tests/unit/test_aggregator.py`](../../tests/unit/test_aggregator.py)
- Comando: `.venv/bin/pytest`

---

## 9. Pendiente real
- Ninguno.

---
> Creado: 2026-10-28 · Última revisión: 2026-10-28
