# Módulo: `collectors` (`src/social_stats/collectors/`)

Interfaz común (`BaseCollector`) y proveedores desacoplados de recolección asíncrona de métricas por red social.

---

## 1. Qué hace y qué NO hace

### 1.1. Qué hace
- Define el contrato abstracto `BaseCollector` (`collect_batch(accounts) -> dict[str, AccountMetrics]`).
- Provee utilidades para registrar errores por cuenta (`record_account_error`) y cuentas deshabilitadas (`record_account_disabled`) sin abortar la recolección del resto de cuentas del lote.
- Permite enriquecer métricas con `SnapshotRepository` (`enrich_with_snapshots`).

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

---

## 5. Dependencias en ambos sentidos
- **Depende de:** `httpx`, `social_stats.config`, `social_stats.models`, `social_stats.storage`.
- **Consumido por:** `services.scheduler`, `main`.

---

## 6. Configuración
Cada subclase utiliza las credenciales e intervalos definidos en `Settings`.

---

## 7. Trampas conocidas y consideraciones de diseño
- Ninguna llamada HTTP debe superar los 15 segundos (`DEFAULT_HTTP_TIMEOUT = httpx.Timeout(15.0, connect=5.0)`).

---

## 8. Tests que lo cubren
- [`tests/unit/test_aggregator.py`](../../tests/unit/test_aggregator.py)
- Comando: `.venv/bin/pytest`

---

## 9. Pendiente real
- Implementación de colectores específicos de Nivel 1 (Fase 2), Nivel 2 (Fase 4) y Nivel 3 (Fase 5).

---
> Creado: 2026-10-28 · Última revisión: 2026-10-28
