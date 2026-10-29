# Decisiones Técnicas y Arquitectónicas

Registro de decisiones técnicas deliberadas del proyecto. Este documento previene que decisiones conscientes de diseño sean revertidas o «arregladas» erróneamente en el futuro.

---

## DT-001: Consumo Estrictamente Unidireccional y de Solo Lectura (Read-Only)
- **Fecha:** 2026-10-28
- **Decisión:** Los clientes (dashboards de escritorio, pantallas, overlays) únicamente leen datos mediante peticiones `GET` en la API REST o escuchan eventos pasivos a través de WebSockets.
- **Motivo:** Evitar vectores de ataque, riesgos de seguridad en red/VPN y complejidad de sincronización bidireccional.
- **Consecuencia:** Queda prohibido exponer endpoints de mutación (`POST`, `PUT`, `DELETE`, `PATCH`). El servidor WebSocket ignora cualquier payload enviado por el cliente tras el handshake inicial.

---

## DT-002: Modelo de Agrupación por Perfiles y Arquitectura Multicanal
- **Fecha:** 2026-10-28
- **Decisión:** Todas las plataformas deben soportar múltiples canales o cuentas (ej. varios canales de YouTube), agrupables bajo identidades lógicas denominadas «Perfiles» (ej. `raupulus`, `proyecto_secundario`).
- **Motivo:** Permitir monitorizar proyectos independientes y perfiles personales desde una misma instancia centralizada, pudiendo solicitar estadísticas globales o filtradas por perfil.
- **Consecuencia:** La configuración declarativa (`profiles.yaml`) define los perfiles. La API REST y los WebSockets admiten filtrado específico por `profile_id`. En WebSockets, la suscripción por perfil se establece en el handshake HTTP de conexión sin requerir mensajes entrantes posteriores.

---

## DT-003: Operación Desatendida sin Re-Autenticación Manual Periódica
- **Fecha:** 2026-10-28
- **Decisión:** Ningún colector puede depender de flujos de login interactivos que caduquen en períodos cortos (ej. tokens OAuth de 7 o 60 días sin renovación automática desatendida).
- **Motivo:** El sistema debe operar 24/7 en un servidor externo sin requerir atención humana continua.
- **Consecuencia:** Se priorizan API Keys permanentes (Google Cloud Data API v3 para YouTube), APIs abiertas sin autenticación (Bluesky AT Protocol, Mastodon REST API), System User Tokens sin caducidad (Meta Graph API para Instagram) o endpoints públicos de sindicación y extracción con caché.

---

## DT-004: Cálculo de Métricas Temporales mediante Snapshots Locales Periódicos
- **Fecha:** 2026-10-28
- **Decisión:** Las métricas de variación («visitas última hora», «visitas último día», «seguidores último día») se calculan localmente mediante series temporales de snapshots en base de datos local (SQLite WAL) en lugar de consultar APIs analíticas externas.
- **Motivo:** Las APIs externas públicas solo devuelven contadores acumulados totales y las APIs de analítica avanzada sufren retrasos de hasta 48 horas y cuotas prohibitivas.
- **Consecuencia:** El motor almacena periódicamente el contador global acumulado y calcula los diferenciales matemáticos ($\Delta_{1h}$ y $\Delta_{24h}$) al vuelo en el servidor.

---

## DT-005: Preservación de Estado en Memoria y Modo Stale ante Errores Externos
- **Fecha:** 2026-10-28
- **Decisión:** Si un colector externo sufre un fallo de red o rate limit, el sistema no bloquea a los demás colectores ni tumba la API. Continúa respondiendo con el último valor válido en caché marcando el estado como `stale`.
- **Motivo:** Garantizar alta disponibilidad y evitar que caídas puntuales de una red social rompan la visualización en la pantalla de escritorio.
- **Consecuencia:** Todos los modelos de datos de métricas deben soportar el estado del colector (`healthy`, `stale`, `error`, `disabled`) y metadatos del último refresco exitoso.

---

## DT-006: Integración de Pulsaciones de Teclas y Clics vía Keycounter API v2 Desacoplada (Read-Only)
- **Fecha:** 2026-10-28 (Actualizado: 2026-10-29)
- **Decisión:** En lugar de abrir endpoints de recepción de pulsaciones en nuestra API (lo que violaría el principio de solo lectura), el servidor actúa exclusivamente como cliente consumidor de la API v2 externa de Keycounter (`KeycounterCollector`), consultando periódicamente el endpoint mediante Bearer Token y sirviendo las métricas hacia la API REST y WebSockets.
- **Motivo:** Mantener estrictamente el modelo Read-Only en la infraestructura propia sin exponer puntos de ingesta ni recibir pulsaciones directas hacia nuestro servidor.
- **Consecuencia:** Se implementó `KeycounterCollector` con soporte para totales históricos (`pulsations_total`, `clicks_total`), métricas de hoy y de la última hora. En el canal WebSocket público (`/ws/public`) se aplica redacción estricta para exponer exclusivamente los totales históricos acumulados, garantizando la privacidad horaria del usuario.

---

## DT-007: Batching Multicanal en YouTube Data API v3 y Campos Nulos para Vistas Globales No Soportadas
- **Fecha:** 2026-10-28
- **Decisión:** El colector de YouTube agrupa hasta 50 `channel_id` en una única llamada HTTP (`channels.list?id=id1,id2...`, 1 unidad de cuota total) independientemente de a qué perfil pertenezca cada canal. Además, los campos `views_total`, `views_last_24h` y `views_last_1h` en `AccountMetrics` y `PlatformSummary` son opcionales (`int | None = None`), devolviendo `null` cuando una red social no ofrece contadores globales de visualizaciones de perfil (Bluesky, Mastodon, Twitter/X, Instagram, TikTok, LinkedIn).
- **Motivo:** Reducir en >90% el consumo de cuota diaria de Google Cloud (10.000 unidades/día) y evitar confundir «métrica no disponible en la plataforma» (`null`) con «0 visitas reales» (`0`).
- **Consecuencia:** `ProfileAggregator` utiliza `_sum_nullable_ints` para ignorar valores `None` al sumar vistas de un perfil y solo reporta un entero en `views_total` / `views_last_24h` / `views_last_1h` si al menos una cuenta de la plataforma o perfil expone vistas no nulas.

---

## DT-008: Arquitectura de Seguridad de 3 Canales (`/ws/public`, `/ws/stats` Privado y `/api/v1/*` Privado)
- **Fecha:** 2026-10-28
- **Decisión:** Separar el consumo en tres canales con políticas de seguridad y exposición diferenciadas:
  1. **WebSocket Público (`/ws/public`):** Accesible sin token para la web pública (`stats.raupulus.dev`), protegido con verificación de `Origin` (`WS_PUBLIC_ALLOWED_ORIGINS`), límite de conexiones por IP (`WS_PUBLIC_MAX_PER_IP`) y global (`WS_PUBLIC_MAX_CONNECTIONS`), `--ws-max-size 1024` y cierre inmediato (`1008`) al primer mensaje enviado por el cliente. Solo expone perfiles/cuentas con `public: true`, redes sociales, cripto y en `keycounter` **exclusivamente los totales históricos acumulados** (`pulsations_total` y `clicks_total`), ocultando `pulsations_today`, `pulsations_last_1h`, `clicks_today` y `clicks_last_1h` para no revelar horarios de actividad en tiempo real.
  2. **WebSocket Privado (`/ws/stats` y `/ws/profiles/{id}`):** Protegido con `API_BEARER_TOKEN`, entrega el 100% de las métricas y eventos sin recortes.
  3. **API REST Privada (`/api/v1/*`):** Protegida con `Authorization: Bearer <API_BEARER_TOKEN>` y ocultación de `/docs`, `/redoc` y `/openapi.json` en producción.
- **Motivo:** Permitir publicar un dashboard público en tiempo real seguro en `stats.raupulus.dev` sin exponer patrones de presencia horaria de teclado/ratón ni abrir la API REST o métricas internas sin autenticación.
- **Consecuencia:** `ProfileAggregator` y `WSManager` filtran y redactan dinámicamente los snapshots y `metric_update` según el canal de cada suscriptor.

---

## DT-009: Cero Credenciales en URLs y Healthcheck Exclusivo de Loopback (`/healthz`)
- **Fecha:** 2026-10-28
- **Decisión:** Prohibir el envío de claves de API o tokens OAuth en parámetros de URL (`?key=`, `?access_token=`), enviándolos únicamente mediante cabeceras HTTP (`X-Goog-Api-Key` en YouTube, `Authorization: Bearer` en Instagram y Keycounter) y aplicando `sanitize_error_message` antes de persistir o registrar cualquier excepción. Además, separar el healthcheck de Docker en `GET /healthz` restringido a loopback (`127.0.0.1` / `::1`) sin cabeceras de proxy inverso.
- **Motivo:** Evitar que una excepción de red de `httpx` o `curl_cffi` filtre tokens secretos en logs, `StateStore` o SQLite, y permitir que Docker verifique la salud del contenedor sin exponer `/api/v1/health` públicamente.
- **Consecuencia:** `Dockerfile` utiliza `http://127.0.0.1:${APP_PORT}/healthz` y cualquier intento de acceder a `/healthz` a través de un proxy inverso externo recibe `403 Forbidden`.

---
> Creado: 2026-10-28 · Última revisión: 2026-10-29
