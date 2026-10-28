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
| `config` | [`config.md`](./config.md) | Configuración de variables de entorno (`.env`) y cargador/validador declarativo de `config/profiles.json` y `config/profiles.yaml` (`enable`, `public`, `interval_minutes`). |
| `models` | [`models.md`](./models.md) | Modelos Pydantic v2 de métricas, estados, perfiles, respuestas REST y eventos WebSocket. |
| `storage` | [`storage.md`](./storage.md) | Base de datos SQLite WAL, motor de snapshots ($\Delta_{1h}$, $\Delta_{24h}$), `StateStore` en memoria y `DiffEngine`. |
| `services` | [`services.md`](./services.md) | Agregador multiperfil (`ProfileAggregator`), planificador (`CollectorScheduler`) y gestor WebSocket (`WSManager`). |
| `collectors` | [`collectors.md`](./collectors.md) | Clase base `BaseCollector` y los 9 proveedores de recolección (redes sociales, cripto y keycounter). |
| `api` / `main` | [`api.md`](./api.md) | Servidor FastAPI Read-Only, seguridad de 3 canales (`/ws/public`, `/ws/stats`, `/api/v1/*`), `/healthz` y montaje estático `public/`. |


---

## 4. Integraciones con APIs Externas (`docs/info/apis/`)

| Plataforma | Documento | Método de Integración |
|---|---|---|
| YouTube | [`apis/youtube.md`](./apis/youtube.md) | Google Data API v3 (Batch multicanal con API Key permanente). |
| Bluesky | [`apis/bluesky.md`](./apis/bluesky.md) | AT Protocol público (`getProfiles` + `getAuthorFeed`). |
| Mastodon | [`apis/mastodon.md`](./apis/mastodon.md) | Instance REST API v1 pública multi-instancia. |
| Twitter / X | [`apis/twitter.md`](./apis/twitter.md) | Syndication API pública (Nivel A) + GraphQL Read-Only Cookie (Nivel B). |
| Instagram | [`apis/instagram.md`](./apis/instagram.md) | Meta Graph API System User Token (Nivel A) + Web Profile API (Nivel B). |
| TikTok | [`apis/tiktok.md`](./apis/tiktok.md) | Hidratación SSR `__UNIVERSAL_DATA_FOR_REHYDRATION__` + Display API v2 auto-refresh. |
| LinkedIn | [`apis/linkedin.md`](./apis/linkedin.md) | Community Management API (`organization`) + Voyager API (`personal`). |
| Binance (Cripto) | [`apis/binance.md`](./apis/binance.md) | Binance Public Market API v3 (`/api/v3/ticker/24hr` en USD/USDT y EUR sin tokens). |
| Keycounter | [`apis/keycounter.md`](./apis/keycounter.md) | API v2 `api.raupulus.dev/api/v2/keycounter/stats` con Bearer token (pulsaciones y clics). |

---
> Creado: 2026-10-28 · Última revisión: 2026-10-28
