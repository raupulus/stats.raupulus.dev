# Módulo: `api` y `main` (`src/social_stats/api/`, `src/social_stats/main.py`)

Capa de exposición Read-Only: servidor FastAPI, endpoints REST v1, endpoints WebSocket con filtrado en handshake y orquestación del ciclo de vida (`lifespan`).

---

## 1. Qué hace y qué NO hace

### 1.1. Qué hace
- Expone los endpoints REST Read-Only bajo `/api/v1`:
  - `GET /api/v1/health`: estado de salud global, SQLite y resumen por colector.
  - `GET /api/v1/profiles`: catálogo de perfiles configurados.
  - `GET /api/v1/stats`: estadísticas globales o filtradas por `?profile=` y `?platform=`.
  - `GET /api/v1/profiles/{profile_id}/stats`: estadísticas agregadas y desglosadas de un perfil (`?platform=`).
  - `GET /api/v1/profiles/{profile_id}/history`: serie temporal de snapshots históricos desde SQLite (`?window=1h|24h|7d|30d`).
- Expone los canales WebSocket Read-Only:
  - `WS /ws/stats` (con `?profile={id}&platform={p}`).
  - `WS /ws/profiles/{profile_id}` (con `?platform={p}`).
- Bloquea mediante middleware cualquier método HTTP distinto de `GET`, `HEAD` y `OPTIONS` devolviendo `405 Method Not Allowed`.
- Valida `profile_id` y `platform` en WebSockets (cerrando con `4004` si no existen), emite el evento `snapshot` inmediatamente al conectar, ignora mensajes entrantes del cliente y desconecta con `1008` si un cliente supera 10 mensajes/minuto.

### 1.2. Qué NO hace
- Jamás acepta mutaciones ni comandos de escritura desde los clientes.

---

## 2. Modelo de datos
- Utiliza los esquemas de `social_stats.models.api` (`HealthResponse`, `ProfilesCatalogResponse`, `GlobalStatsResponse`, `ProfileHistoryResponse`, `WSEventEnvelope`) y `ProfileStats`.

---

## 3. Flujos principales
1. Al iniciar FastAPI (`lifespan`), se conecta SQLite en modo WAL, se carga `profiles.yaml`, se hidrata `StateStore` desde `account_latest_state`, y se inician `WSManager.start_heartbeat()` y `CollectorScheduler.start()`.
2. En peticiones REST `GET`, las rutas consultan `ProfileAggregator` en $O(1)$ o `SnapshotRepository.get_history()`.
3. En conexiones WebSocket, `WSManager.connect()` envía el `snapshot` inicial y registra la suscripción para recibir `metric_update`, `collector_status` y `heartbeat`.

---

## 4. Puntos de entrada (Auth, permisos y límites)
- `create_app(...) -> FastAPI` y objeto `app` en `social_stats.main`.
- Función CLI `run()` invocada por el script `social-stats`.
- Límite anti-flooding en WebSockets: máximo 10 mensajes entrantes ignorados por minuto por cliente antes de cierre `1008`.

---

## 5. Dependencias en ambos sentidos
- **Depende de:** `fastapi`, `uvicorn`, `social_stats.config`, `social_stats.models`, `social_stats.storage`, `social_stats.services`, `social_stats.collectors`.
- **Consumido por:** Clientes externos (dashboards, pantallas de escritorio, monitores) y servidor ASGI (`uvicorn`).

---

## 6. Configuración
| Variable / Parámetro | Tipo | Valor por defecto | Efecto / Comportamiento |
|---|---|---|---|
| `APP_HOST` | `str` | `"0.0.0.0"` | Host de escucha de Uvicorn |
| `APP_PORT` | `int` | `8000` | Puerto de escucha de Uvicorn |
| `CORS_ALLOWED_ORIGINS` | `str` | `"*"` | Orígenes permitidos en `CORSMiddleware` |

---

## 7. Trampas conocidas y consideraciones de diseño
- Si `config/profiles.yaml` no existe en entorno local de pruebas, `main.py` recurre automáticamente a `config/profiles.example.yaml`.

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
