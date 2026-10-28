# Integración de API: Keycounter (`api.raupulus.dev`)

- **Fuente oficial:** `https://api.raupulus.dev/api/v2/keycounter/stats`
- **Colector:** [`KeycounterCollector`](../../../src/social_stats/collectors/keycounter.py)
- **Estado:** ✅ **Verificado empíricamente en vivo contra producción** (2026-10-28 22:12 UTC). La llamada `GET https://api.raupulus.dev/api/v2/keycounter/stats` con cabecera Bearer Token responde `HTTP 200 OK` con formato `application/json` conforme a la especificación, alimentando métricas de pulsaciones (`lifetime`, `today`, `last_hour`) y clics de ratón en tiempo real.

---

## 1. Estrategia de Integración
- **Método y Endpoint:** `GET https://api.raupulus.dev/api/v2/keycounter/stats` (configurable mediante `KEYCOUNTER_API_URL` o campo `instance` por cuenta).
- **Cabeceras obligatorias:**
  - `Authorization: Bearer <KEYCOUNTER_API_TOKEN>`
  - `Accept: application/json`
- **Límite de tasa (Rate Limit):** 60 peticiones/minuto por token (`POLL_INTERVAL_KEYCOUNTER=60` por defecto, o `"interval_minutes": 1` en `config/profiles.json`).
- **Soporte multicuenta:** Mediante `credentials_ref` (ej. `"MAIN"` lee `KEYCOUNTER_API_TOKEN`, `"WORK"` lee `KEYCOUNTER_WORK_API_TOKEN`).

---

## 2. Estructura de Respuesta y Mapeo a `AccountMetrics`

### 2.1. Payload `200 OK`
```json
{
  "success": true,
  "message": "Operación exitosa",
  "data": {
    "user_id": 1,
    "lifetime_pulsations": 12845620,
    "today_pulsations": 15420,
    "last_hour_pulsations": 1850,
    "lifetime_clicks": 450120,
    "today_clicks": 1200,
    "last_hour_clicks": 150,
    "today_from": "2026-10-28T00:00:00.000000Z",
    "last_hour_from": "2026-10-28T21:00:00.000000Z",
    "generated_at": "2026-10-28T22:00:00.000000Z"
  }
}
```

### 2.2. Mapeo de Campos
- `pulsations_total`: `int(data["lifetime_pulsations"])`
- `pulsations_today`: `int(data["today_pulsations"])`
- `pulsations_last_1h`: `int(data["last_hour_pulsations"])`
- `clicks_total`: `int(data["lifetime_clicks"])`
- `clicks_today`: `int(data["today_clicks"])`
- `clicks_last_1h`: `int(data["last_hour_clicks"])`
- `window_1h_complete`: `True`
- `window_24h_complete`: `True`

---
> Creado: 2026-10-28 · Última revisión: 2026-10-28
