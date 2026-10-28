# Notas de Evolución: Conector de Pulsaciones de Teclas y Clics (`KeycounterCollector`)

---

## 1. Implementado: API v2 de Keycounter (`KeycounterCollector`)
- **Estado:** ✅ **Implementado** en [`src/social_stats/collectors/keycounter.py`](../../src/social_stats/collectors/keycounter.py) y documentado en [`docs/info/apis/keycounter.md`](../info/apis/keycounter.md).
- Consulta periódicamente `GET https://api.raupulus.dev/api/v2/keycounter/stats` con `Authorization: Bearer <TOKEN>` y `Accept: application/json`, exponiendo `pulsations_total`, `pulsations_today`, `pulsations_last_1h`, `clicks_total`, `clicks_today` y `clicks_last_1h` tanto en `GET /api/v1/keycounter`, `GET /api/v1/stats`, `GET /api/v1/profiles/{id}/stats` como en tiempo real por WebSockets.

---
> Creado: 2026-10-28 · Última revisión: 2026-10-28
