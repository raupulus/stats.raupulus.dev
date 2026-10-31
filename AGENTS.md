# AGENTS.md

Contexto, reglas y directrices técnicas para agentes de IA que trabajen en este repositorio. Léelo completamente antes de realizar cualquier cambio.

---

## 1. Qué es este proyecto

Una herramienta empaquetada en un contenedor **Docker** y desarrollada en **Python** que monitoriza y centraliza estadísticas en tiempo real de **14 proveedores**: redes sociales, canales, streaming y forjas Git (`YouTube`, `Twitch`, `GitHub`, `GitLab`, `Telegram`, `Bluesky`, `Mastodon`, `Twitter/X`, `Instagram`, `TikTok`, `Facebook`, `LinkedIn`), cripto spot global (`BTC`, `ADA`) y contadores de pulsaciones/clics (`Keycounter`), sirviendo esta información mediante una **arquitectura de seguridad de 3 canales**:

1. **Canal 1 — Público en Internet (`public/` + `WS /ws/public`):** Dashboard web público estático (`public/`) conectado por WebSocket público de solo lectura (`/ws/public`) con validación de `Origin`, límites de conexión por IP/global y exposición exclusiva de cuentas públicas, cripto global y totales históricos acumulados de Keycounter (`pulsations_total` y `clicks_total`).
2. **Canal 2 — WebSocket Privado (`WS /ws/stats` y `WS /ws/profiles/{id}`):** Requiere autenticación `API_BEARER_TOKEN` y entrega el 100% de las métricas y eventos en tiempo real.
3. **Canal 3 — API REST Privada (`GET /api/v1/*`):** Requiere `Authorization: Bearer <API_BEARER_TOKEN>` para consumo desde dispositivos IoT, pantallas de escritorio o scripts en red local/VPN (junto con `GET /healthz` restringido a loopback local para Docker).

- **Arquitectura de consumo:** Estrictamente **unidireccional y de solo lectura**. Los clientes solo consultan datos a través de **API REST** y escuchan eventos en tiempo real mediante **WebSockets**. Los clientes nunca envían mutaciones ni datos al servidor.
- **Mantenedor:** @raupulus · contacto público: `public@raupulus.dev`

---

## 2. Reglas permanentes y de seguridad

1. **Protección estricta de privacidad y datos personales:**
   * **Correo personal estrictamente prohibido:** NUNCA utilizar bajo ningún concepto ningún correo personal o privado del creador.
   * **Único correo público permitido:** El ÚNICO correo que puede utilizarse o escribirse en proyectos públicos, documentación, commits, metadatos, avisos legales o menciones es: `public@raupulus.dev`.
   * **Sin credenciales en git:** Claves de API de redes sociales, tokens de OAuth, secretos de sesión o credenciales locales NUNCA deben commitearse. Siempre se manejarán vía variables de entorno (`.env` gitignorado) o gestores de secretos.
   * **Sin datos sensibles:** No exponer nombres reales completos, IPs privadas, rutas de carpetas de usuario del sistema host ni información personal.

2. **Dirección de flujo de datos:**
   * Los clientes solo consumen datos (Read-Only). No habilitar endpoints REST de escritura ni mensajes entrantes por WebSockets con capacidad de mutación o ejecución remota.

3. **Estructura y control de versiones:**
   * `docs/planning/` está excluido del control de versiones (`.gitignore`) para notas de diseño internas, borradores y planificación en progreso.
   * `docs/` sí se versiona para documentación técnica formal y estable.
   * No commitear artefactos de IDEs, cachés de Python (`__pycache__`, `.pytest_cache`), entornos virtuales (`.venv`) ni ficheros de estado local de Docker.

4. **Commits automáticos agrupados por funcionalidad:**
   * Realizar commits automáticamente por cada grupo de funcionalidades o tareas cerradas **antes de cambiar de contexto**, de modo que todos los cambios relacionados (código, configuración, tests y documentación) vayan siempre agrupados en commits atómicos y descriptivos.
   * Nunca mezclar tareas de diferentes funcionalidades, refactorizaciones no relacionadas o configuraciones ajenas en un mismo commit.
   * Comprobar y garantizar la ausencia total de datos personales privados, rutas del host o credenciales antes de cada commit.

---

## 3. Arquitectura del sistema (Planificación)

```
┌────────────────────────────────────────────────────────────────────────┐
│                          DOCKER CONTAINER (Python)                     │
│                                                                        │
│  ┌───────────────────────┐             ┌────────────────────────────┐  │
│  │   Collectors / Tasks  │             │        In-Memory Cache     │  │
│  │  - Social APIs / Scrap│ ──────────► │       / Data Aggregator    │  │
│  │  - Keystrokes (Agent) │             └─────────────┬──────────────┘  │
│  └───────────────────────┘                           │                 │
│                                                      ▼                 │
│                                        ┌────────────────────────────┐  │
│                                        │     FastAPI / WebSocket    │  │
│                                        │           Server           │  │
│                                        └─────────────┬──────────────┘  │
└──────────────────────────────────────────────────────┼─────────────────┘
                                                       │
                                 VPN / Local Network   │
                                                       ▼
                                         ┌───────────────────────────┐
                                         │   Read-Only Clients       │
                                         │  - REST API Polling       │
                                         │  - WebSockets Stream      │
                                         └───────────────────────────┘
```

- **Runtime:** Python 3.12+ en contenedor Docker (`python:3.12-slim` multi-stage con usuario `appuser` sin privilegios).
- **Framework:** FastAPI + `uvicorn[standard]` (REST API v1 y WebSockets asíncronos Read-Only).
- **Almacenamiento/Estado:** Caché en memoria (`StateStore`) + persistencia histórica SQLite en modo `WAL` (`data/stats.db`) para cálculo de $\Delta_{1h}$ y $\Delta_{24h}$.

### 3.1. Árbol de Estructura Real del Repositorio

```text
social-stats-api-websockets/
├── .dockerignore
├── .env.example
├── .gitignore
├── AGENTS.md
├── CLAUDE.md
├── Dockerfile
├── LICENSE
├── README.md
├── config/
│   ├── profiles.example.json
│   └── profiles.example.yaml
├── docker-compose.yml
├── docs/
│   ├── .gitkeep
│   ├── deploys/
│   │   └── docker-y-credenciales.md
│   ├── future/
│   │   └── server_metrics.md
│   ├── images/
│   │   ├── banner.webp
│   │   ├── github-social-preview-1280x640.png
│   │   ├── github-social-preview.svg
│   │   ├── gitlab-avatar-192x192.png
│   │   ├── gitlab-avatar-192x192.webp
│   │   └── gitlab-avatar.svg
│   └── info/
│       ├── COMPONENTS.md
│       ├── DESIGN.md
│       ├── README.md
│       ├── _MODULE_TEMPLATE.md
│       ├── api.md
│       ├── collectors.md
│       ├── commands.md
│       ├── config.md
│       ├── decisiones-tecnicas.md
│       ├── models.md
│       ├── services.md
│       ├── storage.md
│       └── apis/
│           ├── binance.md
│           ├── bluesky.md
│           ├── facebook.md
│           ├── github.md
│           ├── gitlab.md
│           ├── instagram.md
│           ├── keycounter.md
│           ├── linkedin.md
│           ├── mastodon.md
│           ├── telegram.md
│           ├── tiktok.md
│           ├── twitch.md
│           ├── twitter.md
│           └── youtube.md
├── pyproject.toml
├── public/
│   ├── .well-known/
│   │   ├── ai-catalog.json
│   │   └── ard.json
│   ├── css/
│   │   └── styles.css
│   ├── favicon.svg
│   ├── icon-192.png
│   ├── icon-192.webp
│   ├── images/
│   │   └── platforms/
│   │       ├── ada.webp
│   │       ├── bluesky.webp
│   │       ├── btc.webp
│   │       ├── facebook.webp
│   │       ├── github.webp
│   │       ├── gitlab.webp
│   │       ├── instagram.webp
│   │       ├── linkedin.webp
│   │       ├── mastodon.webp
│   │       ├── telegram.webp
│   │       ├── tiktok.webp
│   │       ├── twitch.webp
│   │       ├── twitter.webp
│   │       └── youtube.webp
│   ├── index.html
│   ├── index.md
│   ├── js/
│   │   └── app.js
│   ├── llms.txt
│   ├── logo.svg
│   ├── og-preview.png
│   ├── og-preview.webp
│   ├── robots.txt
│   ├── site.webmanifest
│   └── sitemap.xml
├── src/
│   └── social_stats/
│       ├── __init__.py
│       ├── main.py
│       ├── py.typed
│       ├── api/
│       │   ├── __init__.py
│       │   ├── router.py
│       │   ├── routes_health.py
│       │   ├── routes_stats.py
│       │   ├── routes_ws.py
│       │   └── security.py
│       ├── collectors/
│       │   ├── __init__.py
│       │   ├── base.py
│       │   ├── bluesky.py
│       │   ├── crypto.py
│       │   ├── facebook.py
│       │   ├── github.py
│       │   ├── gitlab.py
│       │   ├── instagram.py
│       │   ├── keycounter.py
│       │   ├── linkedin.py
│       │   ├── mastodon.py
│       │   ├── telegram.py
│       │   ├── tiktok.py
│       │   ├── twitch.py
│       │   ├── twitter.py
│       │   └── youtube.py
│       ├── config/
│       │   ├── __init__.py
│       │   ├── profiles.py
│       │   └── settings.py
│       ├── models/
│       │   ├── __init__.py
│       │   ├── api.py
│       │   ├── enums.py
│       │   └── metrics.py
│       ├── services/
│       │   ├── __init__.py
│       │   ├── aggregator.py
│       │   ├── scheduler.py
│       │   └── ws_manager.py
│       └── storage/
│           ├── __init__.py
│           ├── database.py
│           ├── snapshot_repo.py
│           └── state_store.py
└── tests/
    ├── conftest.py
    ├── integration/
    │   ├── test_rest_api.py
    │   └── test_websockets.py
    └── unit/
        ├── test_aggregator.py
        ├── test_profiles_config.py
        ├── test_snapshot_deltas.py
        └── collectors/
            ├── test_bluesky.py
            ├── test_crypto.py
            ├── test_facebook.py
            ├── test_github.py
            ├── test_gitlab.py
            ├── test_instagram.py
            ├── test_keycounter.py
            ├── test_linkedin.py
            ├── test_mastodon.py
            ├── test_telegram.py
            ├── test_tiktok.py
            ├── test_twitch.py
            ├── test_twitter.py
            └── test_youtube.py
```

---

## 4. Convenciones de código y desarrollo

- **Tipado estricto:** Uso de `typing` y modelos `Pydantic` para todos los payloads de datos devueltos por la API y WebSockets.
- **Gestión de errores:** Si un colector de una red social falla o experimenta rate limit, el sistema debe responder con el último dato conocido en caché (stale data) indicando el estado del collector, sin tumbar el servicio ni las demás métricas.
- **Modularidad:** Cada fuente de métricas (YouTube, Twitter, Instagram, Bluesky, Mastodon, TikTok, LinkedIn, GitHub, GitLab, Telegram, Twitch, Facebook, Crypto, Keycounter) es un módulo/proveedor desacoplado con una interfaz común (`BaseCollector`).

---

## 5. Protocolo de Documentación `docs/`

Cualquier agente que trabaje en este repositorio debe aplicar este protocolo de forma permanente.

### 5.1. Estructura de `docs/`
- `docs/info/` — Documentación técnica **VIVA** de este proyecto:
  - `README.md` (índice maestro de la documentación viva).
  - `_MODULE_TEMPLATE.md` (plantilla obligatoria para módulos nuevos).
  - `DESIGN.md` (guía de diseño visual para dashboards y pantalla de escritorio).
  - `COMPONENTS.md` (catálogo de componentes de interfaz).
  - `commands.md` (inventario de comandos y scripts ejecutables).
  - `decisiones-tecnicas.md` (registro de decisiones técnicas deliberadas).
  - `<modulo>.md` (un documento por módulo real implementado en `src/`).
  - `apis/<api>.md` (cómo integra el proyecto cada API de terceros).
- `docs/apis/<api>/` — Documentación oficial destilada y verificada de terceros (`README.md`, `00-fundamentos.md`, `ERRATAS.md`, `LIMITACIONES.md`, etc.).
- `docs/planning/` — [NO GIT · EFÍMERO] Planificaciones de fases `<NN>-<fase>.md`, `dudas/` y `archived/`.
- `docs/auditorias/` — [NO GIT · EFÍMERO] Informes de auditoría técnica.
- `docs/future/` — Funcionalidades o ideas decididas pero aplazadas.
- `docs/deploys/` — Guías operativas de despliegue.

### 5.2. Reglas Permanentes de Documentación
1. **Documentar es parte de la tarea:** Ninguna tarea está terminada si su documentación no se actualiza **en el mismo commit que el código**.
2. **Jerarquía de verdad sobre el estado actual:** `código ejecutable > docs/info/ > AGENTS.md > el resto`. Los directorios `docs/planning/`, `docs/future/` y `docs/auditorias/` **nunca** son fuente de verdad del estado actual.
3. **Discrepancia entre documentación y código:** Se corrige en el commit en que se detecta, nunca se posterga.
4. **Ciclo de vida de módulos:** Tocas un módulo → actualizas su `.md`. Creas uno → lo creas a partir de `_MODULE_TEMPLATE.md` y lo indexas en `docs/info/README.md` y en este `AGENTS.md`. Eliminas uno → borras su `.md` y lo quitas de todos los índices.
5. **Pie de metadatos obligatorio:** Todo archivo bajo `docs/` en cualquier subdirectorio debe terminar con esta línea exacta tras un separador `---`:
   `> Creado: YYYY-MM-DD · Última revisión: YYYY-MM-DD`
   La fecha de creación jamás se altera; la de revisión se actualiza en el mismo commit que el documento.
6. **Checklists verificados:** En cualquier planificación, `[x]` significa **verificado funcionando y cumpliendo con tests**. Escribir el código no marca la casilla.
7. **Ciclo de lo efímero:** `docs/planning/` y `docs/auditorias/` son borradores de un único desarrollador. Ciclo: crear → trabajar → verificar → promocionar lo duradero → **borrar**.
8. **Promoción obligatoria antes de borrar:** Antes de borrar lo efímero, promociona: comportamiento a `docs/info/<modulo>.md`, decisiones a `docs/info/decisiones-tecnicas.md`, trampas a `AGENTS.md`, ideas aplazadas a `docs/future/`.
9. **Cero enlaces rotos:** Nada versionado en Git puede enlazar a `docs/planning/` ni `docs/auditorias/`. Ambos directorios deben permanecer ignorados en `.gitignore`.
10. **Lectura dirigida:** Al trabajar en un módulo lees **solo su `.md`**. Si tocas frontend añades `DESIGN.md` y `COMPONENTS.md`. Si tocas una API externa añades `docs/apis/<api>/`. No leas el resto de `docs/info/`, `docs/future/` ni `archived/`.
11. **Verificación empírica:** Nunca des por buena una especificación externa sin verificarla con una petición real. Lo no comprobado se marca explícitamente como `⚠️ sin verificar`.
12. **Convención de idioma:** Documentación, comentarios y textos de cara al usuario en **español**. Identificadores de código, nombres de archivo/directorio y logs en **inglés** (salvo payloads devueltos por APIs de terceros que se respetan literalmente).
13. **Atribución estricta:** Autoría y commits exclusivamente atribuidos a `@raupulus` / `public@raupulus.dev`. Sin firmas automáticas de herramientas o agentes (`Co-Authored-By`, `Generated by`, etc.).

### 5.3. Índice Maestro Actual de `docs/info/`
- [`docs/info/README.md`](docs/info/README.md) — Índice maestro
- [`docs/info/_MODULE_TEMPLATE.md`](docs/info/_MODULE_TEMPLATE.md) — Plantilla para nuevos módulos
- [`docs/info/DESIGN.md`](docs/info/DESIGN.md) — Guía de diseño visual para dashboards
- [`docs/info/COMPONENTS.md`](docs/info/COMPONENTS.md) — Catálogo de componentes de presentación
- [`docs/info/commands.md`](docs/info/commands.md) — Inventario de comandos CLI
- [`docs/info/decisiones-tecnicas.md`](docs/info/decisiones-tecnicas.md) — Registro de decisiones técnicas
- [`docs/deploys/docker-y-credenciales.md`](docs/deploys/docker-y-credenciales.md) — Guía operativa de despliegue Docker y credenciales permanentes
- *Módulos implementados en `src/`:*
  - [`docs/info/config.md`](docs/info/config.md) — Configuración de variables de entorno y perfiles declarativos (`profiles.json` / `profiles.yaml`, `enable`, `interval_minutes`)
  - [`docs/info/models.md`](docs/info/models.md) — Modelos de dominio y esquemas Pydantic REST/WebSocket
  - [`docs/info/storage.md`](docs/info/storage.md) — Motor SQLite WAL, cálculo de deltas ($\Delta_{1h}$, $\Delta_{24h}$), `StateStore` y `DiffEngine`
  - [`docs/info/services.md`](docs/info/services.md) — `ProfileAggregator`, `CollectorScheduler` y `WSManager`
  - [`docs/info/collectors.md`](docs/info/collectors.md) — Interfaz `BaseCollector` y los 14 colectores por plataforma (redes sociales, forjas Git, canales, streaming, cripto y keycounter)
  - [`docs/info/api.md`](docs/info/api.md) — Servidor FastAPI Read-Only, rutas REST v1 y WebSockets

### 5.4. Checklist Obligatorio antes de Cerrar Cualquier Tarea
- [x] Commits realizados automáticamente agrupando cada funcionalidad cerrada antes de cambiar de contexto
- [x] Documentación del módulo tocado actualizada en el **mismo commit**
- [x] Fechas de «Última revisión» al día en todos los archivos `.md` tocados bajo `docs/`
- [x] Módulos nuevos creados desde `_MODULE_TEMPLATE.md` e indexados en `docs/info/README.md` y `AGENTS.md`
- [x] Módulos eliminados retirados de todos los índices
- [x] Ningún archivo versionado enlaza a `docs/planning/` ni a `docs/auditorias/`
- [x] `/docs/planning/` y `/docs/auditorias/` permanecen en `.gitignore`
- [x] Lo duradero de planificaciones cerradas promocionado y los archivos efímeros borrados
- [x] Checklists `[x]` verificados empíricamente, no asumidos
- [x] Árbol de estructura de directorios en `AGENTS.md` refleja la realidad del repositorio
