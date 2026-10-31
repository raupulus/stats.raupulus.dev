# stats.raupulus.dev · Telemetría y Estadísticas de Proyectos en Tiempo Real

> Nodo público de telemetría unidireccional (`Read-Only`) que centraliza y transmite en tiempo real las métricas de audiencia, desarrollo Open Source, criptomonedas spot (`BTC`, `ADA`) y contadores de periféricos (`Keycounter`) de **Raúl Caro Pastorino (@raupulus)** y sus proyectos.

## 1. Arquitectura de Exposición Pública

- **URL Canónica:** [https://stats.raupulus.dev/](https://stats.raupulus.dev/)
- **Stream WebSocket Público (Solo Lectura):** `wss://stats.raupulus.dev/ws/public`
  - Eventos emitidos por el servidor: `snapshot` (estado inicial completo al conectar), `metric_update` (diferenciales en tiempo real cuando cambia una métrica) y `heartbeat` (pulso periódico con `uptime_seconds`).
  - Parámetros opcionales de filtrado: `?profile=<id>&platform=<plataforma>`.
  - Estrictamente unidireccional: cualquier trama enviada desde el cliente cierra la conexión inmediatamente con código `1008 Policy Violation`.

## 2. Proveedores y Métricas Monitorizadas (14 Colectores)

1. **Redes Sociales, Canales y Streaming:** `YouTube`, `Twitch` (estado `EN DIRECTO` y espectadores simultáneos), `Telegram`, `Twitter/X`, `Instagram`, `TikTok`, `Facebook`, `Bluesky`, `Mastodon` y `LinkedIn`.
2. **Forjas Git Open Source:** `GitHub` y `GitLab` (seguidores, repositorios/proyectos públicos totales, estrellas `★` acumuladas y forks totales).
3. **Mercado Cripto Spot Global:** `Bitcoin (BTC)` y `Cardano (ADA)` con cotización en vivo y rango 24h tanto en **USD ($)** como en **EUR (€)**.
4. **Keycounter (Telemetría de Entrada):** Totales históricos acumulados de pulsaciones de teclado (`pulsations_total`) y clics de ratón (`clicks_total`) por perfil.

## 3. Enlaces y Documentación para Agentes

- [llms.txt](https://stats.raupulus.dev/llms.txt): Resumen estructurado del dominio para LLMs.
- [Catálogo ARD (/.well-known/ai-catalog.json)](https://stats.raupulus.dev/.well-known/ai-catalog.json): Descubrimiento de recursos agénticos.
- [Web Oficial de Raúl Caro Pastorino](https://raupulus.dev/) · Contacto público: `public@raupulus.dev`
