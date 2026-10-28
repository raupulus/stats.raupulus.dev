# Integración API Externa: YouTube Data API v3 (`YouTubeCollector`)

Integración en el proyecto con Google YouTube Data API v3 para recolección multicanal en lote.

---

## 1. Endpoints Utilizados
1. **Resolución opcional de `@handle` a `channel_id` (`UC...`):**
   - `GET https://www.googleapis.com/youtube/v3/channels?part=id&forHandle={handle}&key={YOUTUBE_API_KEY}`
   - Se ejecuta una única vez por cada canal configurado solo con `handle` y se cachea en memoria (`_handle_to_channel_id`).
2. **Consulta Batch Multicanal (hasta 50 canales por llamada):**
   - `GET https://www.googleapis.com/youtube/v3/channels?part=statistics,snippet&id=UCxxx1,UCxxx2&key={YOUTUBE_API_KEY}`

---

## 2. Mapeo de Campos
- `statistics.subscriberCount` $\rightarrow$ `followers_total` (`None` si `hiddenSubscriberCount == true`).
- `statistics.videoCount` $\rightarrow$ `posts_total`.
- `statistics.viewCount` $\rightarrow$ `views_total`.
- `followers_last_24h`, `views_last_24h`, `views_last_1h` $\rightarrow$ calculados por `SnapshotRepository`.

---

## 3. Autenticación y Cuotas
- Variable de entorno: `YOUTUBE_API_KEY` (API Key permanente de Google Cloud Console, sin caducidad).
- Coste de cuota: 1 unidad por petición batch de hasta 50 canales (~288 unidades/día con intervalo de 300s, < 3% del nivel gratuito de 10.000 unidades/día).

---
> Creado: 2026-10-28 · Última revisión: 2026-10-28
