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

### Endpoints REST Principales (Read-Only)
- `GET /api/v1/health` — Salud del contenedor, base de datos SQLite y estado de colectores.
- `GET /api/v1/profiles` — Catálogo de perfiles configurados.
- `GET /api/v1/crypto` — Cotizaciones spot y estadísticas 24h de criptomonedas (`BTC`, `ADA`) en USD y EUR.
- `GET /api/v1/keycounter` — Estadísticas de pulsaciones de teclas y clics de ratón (totales, hoy y última hora).
- `GET /api/v1/stats` — Estadísticas globales (filtrables con `?profile=` y `?platform=`).
- `GET /api/v1/profiles/{profile_id}/stats` — Estadísticas agregadas y por cuenta de un perfil.
- `GET /api/v1/profiles/{profile_id}/history?window=24h` — Serie temporal histórica (`1h`, `24h`, `7d`, `30d`).

### Canales WebSocket en Tiempo Real (Read-Only)
- `ws://<host>:8000/ws/stats` — Stream global de todos los perfiles (`?profile={id}&platform={p}`).
- `ws://<host>:8000/ws/profiles/{profile_id}` — Stream exclusivo de un perfil específico.

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
