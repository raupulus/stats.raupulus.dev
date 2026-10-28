<p align="center">
  <img src="docs/images/banner.webp" alt="stats.raupulus.dev - Social Stats API & WebSockets" width="100%">
</p>

# Social Stats API & WebSockets

Herramienta centralizada, empaquetada en un contenedor **Docker** y desarrollada en **Python**, diseñada para monitorizar estadísticas de redes sociales (YouTube, Bluesky, Mastodon, Twitter/X, Instagram, TikTok, etc.) y métricas de sistema, sirviendo la información a paneles, dashboards y pantallas de escritorio en tiempo real.

El servicio está concebido para operar en entornos locales y redes privadas accesibles exclusivamente mediante **VPN**.

---

## Características Principales

- **Arquitectura Estrictamente Read-Only (Unidireccional):**
  - Los clientes únicamente consumen información a través de **API REST** (consultas de estado puntual e histórico) y **WebSockets** (streaming continuo de eventos en tiempo real).
  - Los clientes nunca envían comandos, mutaciones ni datos al servidor.
- **Multicanal y Agrupación por Perfiles:**
  - Soporte nativo para múltiples cuentas y canales por cada red social.
  - Organización declarativa mediante perfiles lógicos (ej. perfil personal `raupulus`, perfiles de proyectos secundarios), permitiendo consultar o suscribirse al estado global o a un perfil específico.
- **Métricas Temporales en Tiempo Real ($\Delta_{1h}$ y $\Delta_{24h}$):**
  - Cálculo exacto en el servidor de variaciones de última hora y último día mediante series temporales de snapshots locales, eliminando la dependencia de APIs analíticas externas con retrasos de 48 horas.
- **Operación Desatendida (Zero Manual Relogin):**
  - Diseñado para funcionar 24/7 sin interrupciones ni flujos de login interactivos periódicos.
- **Tolerancia a Fallos y Caché Resiliente:**
  - Respuestas inmediatas con el último dato válido conocido (`stale data`) ante caídas o límites de cuota de proveedores externos, sin afectar al resto de plataformas.

---

## Arquitectura General

```text
┌────────────────────────────────────────────────────────────────────────┐
│                          DOCKER CONTAINER (Python)                     │
│                                                                        │
│  ┌───────────────────────┐             ┌────────────────────────────┐  │
│  │   Async Collectors    │             │        In-Memory Cache     │  │
│  │  - YouTube (Batch)    │ ──────────► │       / Data Aggregator    │  │
│  │  - Bluesky / Mastodon │             └─────────────┬──────────────┘  │
│  │  - Twitter / Instagram│                           │                 │
│  └───────────────────────┘                           ▼                 │
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

---

## Inicio Rápido (Docker Compose)

```bash
cp .env.example .env
cp config/profiles.example.json config/profiles.json
mkdir -p data
docker compose up --build -d
```

### Arquitectura de Seguridad de 3 Canales (Read-Only)

1. **Web Pública y WebSocket Público (`public/` + `WS /ws/public`):**
   - El directorio `public/` actúa como `DocumentRoot` aislado para `https://stats.raupulus.dev/` (o servido automáticamente en `/` en entorno local).
   - `WS /ws/public` no requiere token, pero aplica validación estricta de `Origin` (`WS_PUBLIC_ALLOWED_ORIGINS`), límite de conexiones por IP (`WS_PUBLIC_MAX_PER_IP`), límite global (`WS_PUBLIC_MAX_CONNECTIONS`) y cierre inmediato (`1008`) al primer mensaje entrante del cliente.
   - Expone únicamente perfiles/cuentas con `"public": true`, todas las redes sociales públicas, cripto spot (`BTC`, `ADA` en USD y EUR) y en `keycounter` **solo los totales acumulados históricos** (`pulsations_total` y `clicks_total`).
2. **WebSocket Privado Autenticado (`WS /ws/stats` y `WS /ws/profiles/{profile_id}`):**
   - Requiere `API_BEARER_TOKEN` (`Authorization: Bearer <token>`, `Sec-WebSocket-Protocol: bearer, <token>` o `?token=<token>`).
   - Emite el 100% de las métricas sin recortes (incluyendo ventanas 1h y hoy de Keycounter y eventos `collector_status`).
3. **API REST Privada Autenticada (`GET /api/v1/*` con `Authorization: Bearer <API_BEARER_TOKEN>`):**
   - `GET /api/v1/health` — Salud del contenedor, base de datos SQLite y estado detallado de colectores.
   - `GET /api/v1/profiles` — Catálogo de perfiles configurados.
   - `GET /api/v1/crypto` — Cotizaciones spot y estadísticas 24h de criptomonedas (`BTC`, `ADA`) en USD y EUR.
   - `GET /api/v1/keycounter` — Estadísticas completas de pulsaciones de teclas y clics de ratón (totales, hoy y última hora).
   - `GET /api/v1/stats` — Estadísticas globales (filtrables con `?profile=` y `?platform=`).
   - `GET /api/v1/profiles/{profile_id}/stats` — Estadísticas agregadas y por cuenta de un perfil.
   - `GET /api/v1/profiles/{profile_id}/history?window=24h` — Serie temporal histórica (`1h`, `24h`, `7d`, `30d`).
   - *(Healthcheck interno de Docker: `GET /healthz`, restringido exclusivamente a loopback local `127.0.0.1` / `::1` sin proxy inverso).*

---

## Documentación Técnica

La documentación del proyecto sigue un estricto protocolo de actualización continua sincronizado con el código:

- **[Índice Maestro de Documentación Viva (`docs/info/`)](docs/info/README.md):** Estado técnico verificado de módulos, componentes y contratos.
- **[Guía de Despliegue y Credenciales Permanentes (`docs/deploys/docker-y-credenciales.md`)](docs/deploys/docker-y-credenciales.md):** Configuración paso a paso de Docker, VPN y API Keys sin caducidad.
- **[Decisiones Técnicas (`docs/info/decisiones-tecnicas.md`)](docs/info/decisiones-tecnicas.md):** Registro inmutable de decisiones arquitectónicas del sistema.
- **[Guía de Diseño Visual (`docs/info/DESIGN.md`)](docs/info/DESIGN.md):** Pautas de diseño para visualización en pantallas de escritorio.
- **[Catálogo de Componentes (`docs/info/COMPONENTS.md`)](docs/info/COMPONENTS.md):** Especificación de componentes de presentación para dashboards.
- **[Inventario de Comandos (`docs/info/commands.md`)](docs/info/commands.md):** Registro de scripts y comandos de ejecución.

---

## Licencia

Este proyecto está distribuido bajo los términos de la licencia **GNU Affero General Public License v3** ([AGPL-3.0](LICENSE)).

---

## Autor y Créditos

- **Autor:** [@raupulus](https://raupulus.dev)
- **Sitio Web:** [raupulus.dev](https://raupulus.dev)
- **Contacto público:** [public@raupulus.dev](mailto:public@raupulus.dev)
