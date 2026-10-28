# Índice Maestro de Documentación Técnica Viva (`docs/info/`)

Bienvenido a la documentación técnica **viva** del proyecto. Este directorio contiene el estado verificado del sistema y se actualiza en el mismo commit en que se modifica el código correspondiente.

---

## 1. Jerarquía de Verdad del Proyecto
1. **Código fuente ejecutable** (máxima autoridad sobre el comportamiento real).
2. **`docs/info/`** (documentación viva y verificada del estado actual).
3. **`AGENTS.md`** (directrices, convenciones y reglas de desarrollo).
4. `docs/planning/`, `docs/future/` y `docs/auditorias/` **NUNCA** son fuente de verdad del estado actual del sistema.

---

## 2. Índice de Documentos Generales

| Documento | Descripción |
|---|---|
| [`_MODULE_TEMPLATE.md`](./_MODULE_TEMPLATE.md) | Plantilla obligatoria para documentar cualquier módulo nuevo al crearlo. |
| [`decisiones-tecnicas.md`](./decisiones-tecnicas.md) | Registro de decisiones arquitectónicas deliberadas (Read-Only estricto, perfiles, snapshots, etc.). |
| [`commands.md`](./commands.md) | Inventario de comandos CLI y scripts del proyecto. |
| [`DESIGN.md`](./DESIGN.md) | Criterios y directrices de diseño visual para dashboards y pantalla de escritorio. |
| [`COMPONENTS.md`](./COMPONENTS.md) | Catálogo de componentes visuales de interfaz. |

---

## 3. Estado de Módulos Implementados en Código

| Módulo | Archivo | Descripción |
|---|---|---|
| `config` | [`config.md`](./config.md) | Configuración de variables de entorno (`.env`) y cargador/validador declarativo de `config/profiles.yaml`. |
| `models` | [`models.md`](./models.md) | Modelos Pydantic v2 de métricas, estados, perfiles, respuestas REST y eventos WebSocket. |
| `storage` | [`storage.md`](./storage.md) | Base de datos SQLite WAL, motor de snapshots ($\Delta_{1h}$, $\Delta_{24h}$), `StateStore` en memoria y `DiffEngine`. |
| `services` | [`services.md`](./services.md) | Agregador multiperfil (`ProfileAggregator`) y planificador asíncrono (`CollectorScheduler`). |
| `collectors` | [`collectors.md`](./collectors.md) | Clase base `BaseCollector` y proveedores de recolección por red social. |


---

## 4. Integraciones con APIs Externas (`docs/info/apis/`)

> ⚠️ **Estado actual:** Ninguna API externa conectada en código todavía.  
> Cuando se implemente cada colector de red social, se añadirá aquí su correspondiente documento `docs/info/apis/<api>.md` explicando cómo se integra dicha API en el proyecto.

---
> Creado: 2026-10-28 · Última revisión: 2026-10-28
