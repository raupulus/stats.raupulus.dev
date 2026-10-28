# Integración API Externa: LinkedIn (`LinkedInCollector`)

Colector de Nivel 3 aislado para LinkedIn con degradación a estado `disabled` por defecto si no se proveen credenciales.

---

## 1. Modos Soportados
1. **Modo Organización (`account_type: "organization"`):**
   - Requiere `LINKEDIN_ACCESS_TOKEN` (o token persistido en `auth_tokens` de SQLite).
   - Consulta `GET https://api.linkedin.com/rest/organizationalEntityFollowerStatistics` y `GET https://api.linkedin.com/rest/posts`.
2. **Modo Personal (`account_type: "personal"`):**
   - Requiere `LINKEDIN_LI_AT_COOKIE` con intervalo conservador de 3600s (`POLL_INTERVAL_LINKEDIN`).
   - Consulta `GET https://www.linkedin.com/voyager/api/identity/dash/profiles?q=memberIdentity&memberIdentity={handle}`.

---

## 2. Degradación Limpia
- Si una cuenta de LinkedIn no tiene configurada su credencial correspondiente en `.env`, `LinkedInCollector` la registra en `disabled_accounts` y `StateStore` reporta `status: "disabled"` sin disparar alertas de error.

---

## 3. Estado de Verificación Empírica
- Modos `organization`, `personal` y degradación a `status: "disabled"` verificados mediante mocks HTTP deterministas (`respx`) en `tests/unit/collectors/test_linkedin.py`.
- Peticiones en vivo contra `api.linkedin.com/rest/` y `www.linkedin.com/voyager/api/`: `⚠️ sin verificar` con credenciales reales.

---
> Creado: 2026-10-28 · Última revisión: 2026-10-28
