# Módulo: `storage` (`src/social_stats/storage/`)

Capa de persistencia histórica en SQLite (`WAL`), motor matemático de cálculo de variaciones temporales ($\Delta_{1h}$ y $\Delta_{24h}$), caché en memoria (`StateStore`) y motor de detección de cambios (`DiffEngine`).

---

## 1. Qué hace y qué NO hace

### 1.1. Qué hace
- Gestiona la conexión asíncrona a SQLite (`Database`) activando `PRAGMA journal_mode=WAL;` y `PRAGMA synchronous=NORMAL;`.
- Almacena snapshots periódicos en `metric_snapshots` (incluyendo cotizaciones `price_usd` y `price_eur` en `extra_json`), el último estado conocido en `account_latest_state` y tokens auto-renovables en `auth_tokens`.
- Calcula $\Delta_{1h}$ (`views_last_1h`) y $\Delta_{24h}$ (`views_last_24h`, `followers_last_24h`) en `SnapshotRepository` soportando estado nominal, arranque en frío (*warm-up*) y protección frente a paradas prolongadas.
- Mantiene en memoria (`StateStore`) el estado actual de todas las cuentas para lecturas $O(1)$ y preserva métricas previas con estado `stale` cuando ocurre un fallo de recolección.
- Calcula diferencias granulares entre lecturas consecutivas mediante `DiffEngine` (tanto contadores enteros como precios cripto `float`), detectando publicaciones nuevas (`is_new_latest_post = True`) sin producir deltas negativos.

### 1.2. Qué NO hace
- No agrupa cuentas por perfil lógico (responsabilidad de `ProfileAggregator` en `services`).
- No realiza llamadas HTTP a redes sociales.

---

## 2. Modelo de datos
- Tablas SQLite:
  - `metric_snapshots` (con índice compuesto `idx_snapshots_lookup(platform, account_key, timestamp DESC)`).
  - `account_latest_state` (clave primaria `(platform, account_key)`).
  - `auth_tokens` (clave primaria `(provider, credentials_ref)`).
- Estructuras en Python:
  - `DeltaCalculationResult`: `followers_last_24h`, `views_last_24h`, `views_last_1h`, `window_1h_complete`, `window_24h_complete`.
  - `DiffResult`: `is_new_latest_post`, `changes: dict[str, MetricChange]`.
  - `AccountUpdateOutcome`: `state`, `diff`, `status_transition`, `consecutive_failures`.

---

## 3. Flujos principales
1. **Arranque:** `Database.connect()` inicializa el esquema en modo WAL y `StateStore.initialize_from_config_and_db()` hidrata la memoria con `account_latest_state`.
2. **Enriquecimiento de Snapshot:** Antes de insertar la muestra actual en $t_{\text{now}}$, `SnapshotRepository.calculate_deltas()` busca la muestra en $[t_{\text{now}} - W - \text{tol}, t_{\text{now}} - W]$ (o la más antigua en $(t_{\text{now}} - W, t_{\text{now}})$ durante el *warm-up*) e inserta el nuevo snapshot.
3. **Actualización en Memoria:** `StateStore.update_account_success()` ejecuta `DiffEngine.compute_diff()`, actualiza el estado a `healthy` y persiste en `account_latest_state`.
4. **Fallo Resiliente:** `StateStore.record_account_failure()` conserva las métricas previas si existen (`status = stale`) o marca `error` si nunca hubo datos previos.

---

## 4. Puntos de entrada (Auth, permisos y límites)
- `Database(db_path).connect()`, `close()`, `check_health()`, `upsert_latest_state()`, `load_all_latest_states()`, `get_auth_token()`, `upsert_auth_token()`.
- `SnapshotRepository(db).calculate_deltas()`, `insert_snapshot()`, `enrich_and_record()`, `get_history()`, `prune_old_snapshots()`.
- `StateStore(db).initialize_from_config_and_db()`, `update_account_success()`, `record_account_failure()`, `get_account_state()`.

---

## 5. Dependencias en ambos sentidos
- **Depende de:** `aiosqlite`, `social_stats.models`, `social_stats.config`.
- **Consumido por:** `services` (`aggregator`, `scheduler`), `collectors`, `api`, `main`.

---

## 6. Configuración
| Variable / Parámetro | Tipo | Valor por defecto | Efecto / Comportamiento |
|---|---|---|---|
| `SQLITE_DB_PATH` | `Path` | `data/stats.db` | Ruta al archivo SQLite (o `:memory:` en tests) |
| `SNAPSHOT_RETENTION_DAYS` | `int` | `30` | Ventana de retención para `prune_old_snapshots()` |

---

## 7. Trampas conocidas y consideraciones de diseño
- `calculate_deltas()` debe ejecutarse **antes** de `insert_snapshot()` para el mismo timestamp (o usar `enrich_and_record()`), además de incluir la guarda `timestamp < now_ts` en la consulta de calentamiento.
- `Database.execute_write()` serializa todas las escrituras sobre la conexión `aiosqlite` compartida mediante `write_lock` (`asyncio.Lock`) y protege el par `execute` + `commit` con `asyncio.shield` para evitar transacciones a medias si se cancela una tarea durante el apagado.
- Cuando cambia `latest_post.post_id`, `DiffEngine` toma `previous = 0` como línea base del nuevo post para evitar deltas negativos al reemplazar un post antiguo con miles de visitas por uno recién publicado.

---

## 8. Tests que lo cubren
- [`tests/unit/test_snapshot_deltas.py`](../../tests/unit/test_snapshot_deltas.py)
- [`tests/unit/test_aggregator.py`](../../tests/unit/test_aggregator.py)
- Comando: `.venv/bin/pytest tests/unit/test_snapshot_deltas.py tests/unit/test_aggregator.py`

---

## 9. Pendiente real
- Ninguno.

---
> Creado: 2026-10-28 · Última revisión: 2026-10-28
