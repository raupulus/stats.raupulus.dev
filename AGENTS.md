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
