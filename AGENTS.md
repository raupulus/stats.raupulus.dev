# AGENTS.md

Contexto, reglas y directrices técnicas para agentes de IA que trabajen en este repositorio. Léelo completamente antes de realizar cualquier cambio.

---

## 1. Qué es este proyecto

Una herramienta local y accesible exclusivamente mediante VPN, empaquetada en un contenedor **Docker** y desarrollada en **Python**.

Su función es monitorizar y centralizar estadísticas de redes sociales (YouTube, Twitter/X, Instagram, etc.) y recursos locales (como contadores de pulsaciones de teclas / keystrokes), sirviendo esta información a clientes en tiempo real.

- **Arquitectura de consumo:** Estrictamente **unidireccional y de solo lectura**. Los clientes (dashboards, overlays, scripts de monitorización) solo consultan datos a través de **API REST** y escuchan eventos en tiempo real mediante **WebSockets**. Los clientes nunca envían mutaciones ni datos al servidor.
- **Entorno:** Local / VPN privada. Sin exposición pública directa sin túnel/VPN.
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

- **Runtime:** Python 3.12+ en contenedor Docker.
- **Framework sugerido:** FastAPI / Starlette + `websockets` o `uvicorn` (asíncrono nativo para soportar conexiones persistentes con mínimo overhead).
- **Almacenamiento/Estado:** Caché en memoria + persistencia ligera (SQLite / Redis / JSON state file con volumen mapeado) para mantener histórico de métricas.

---

## 4. Convenciones de código y desarrollo

- **Tipado estricto:** Uso de `typing` y modelos `Pydantic` para todos los payloads de datos devueltos por la API y WebSockets.
- **Gestión de errores:** Si un colector de una red social falla o experimenta rate limit, el sistema debe responder con el último dato conocido en caché (stale data) indicando el estado del collector, sin tumbar el servicio ni las demás métricas.
- **Modularidad:** Cada fuente de métricas (YouTube, Twitter, Instagram, Keystrokes) debe ser un módulo/proveedor desacoplado con una interfaz común (`BaseCollector`).

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
- *Módulos implementados en `src/`:* `⚠️ Sin módulos implementados aún`

### 5.4. Checklist Obligatorio antes de Cerrar Cualquier Tarea
- [ ] Documentación del módulo tocado actualizada en el **mismo commit**
- [ ] Fechas de «Última revisión» al día en todos los archivos `.md` tocados bajo `docs/`
- [ ] Módulos nuevos creados desde `_MODULE_TEMPLATE.md` e indexados en `docs/info/README.md` y `AGENTS.md`
- [ ] Módulos eliminados retirados de todos los índices
- [ ] Ningún archivo versionado enlaza a `docs/planning/` ni a `docs/auditorias/`
- [ ] `/docs/planning/` y `/docs/auditorias/` permanecen en `.gitignore`
- [ ] Lo duradero de planificaciones cerradas promocionado y los archivos efímeros borrados
- [ ] Checklists `[x]` verificados empíricamente, no asumidos
- [ ] Árbol de estructura de directorios en `AGENTS.md` refleja la realidad del repositorio
