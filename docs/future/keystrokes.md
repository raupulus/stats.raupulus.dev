# Funcionalidad Pospuesta: Conector de Pulsaciones de Teclas (`KeystrokesCollector`)

Especificación de la Fase 6 (pospuesta deliberadamente hasta estabilizar las Fases 0–5 de redes sociales, según `DT-006`).

---

## 1. Alcance y Restricciones Arquitectónicas
- **Consumo estrictamente Read-Only:** El servidor jamás abrirá endpoints `POST` ni mensajes WebSocket entrantes para recibir pulsaciones desde agentes externos.
- **Fuente de datos:** Un colector `KeystrokesCollector(BaseCollector)` en `src/social_stats/collectors/keystrokes.py` leerá periódicamente en modo de solo lectura desde la base de datos externa del servidor donde ya se centralizan las pulsaciones.
- **Métricas previstas:** `keystrokes_total`, `keystrokes_last_24h` ($\Delta_{24h}$) y `keystrokes_last_1h` ($\Delta_{1h}`), integradas en el perfil correspondiente y emitidas por el mismo flujo REST y WebSockets.

---
> Creado: 2026-10-28 · Última revisión: 2026-10-28
