# Integración API Externa: Facebook Graph API v21.0 + OpenGraph HTML (`FacebookCollector`)

Arquitectura dual para páginas públicas de Facebook con soporte de seguidores y "Me gusta" (`fan_count`).

---

## 1. Endpoints Utilizados
### Nivel A — Meta Graph API v21.0 (Opcional, con System User Page Token permanente)
- `GET https://graph.facebook.com/v21.0/{page_id}?fields=id,name,followers_count,fan_count`
  - Cabecera `Authorization: Bearer {FB_<REF>_ACCESS_TOKEN}` (jamás en query string).

### Nivel B — Fallback Público OpenGraph HTML (`curl_cffi`)
- `GET https://www.facebook.com/{handle}/` con suplantación TLS de navegador (`impersonate="chrome124"`).
- Extracción bilingüe (inglés y español: `followers`/`seguidores`, `likes`/`Me gusta`, sufijos `K`/`M`/`mil`) sobre `<meta property="og:description">` y `<meta name="description">`.

---

## 2. Mapeo de Campos
- `followers_count` (Nivel A) o conteo de seguidores en OpenGraph (Nivel B) $\rightarrow$ `followers_total`.
- `fan_count` (Nivel A) o conteo de `likes` / `Me gusta` en OpenGraph (Nivel B, si la página lo expone) $\rightarrow$ `stars_total`.
- Si una página clásica expone únicamente `likes` pero no `followers`, `followers_total` toma el valor de `likes` como respaldo.

---

## 3. Autenticación y Resiliencia
- No requiere credenciales para páginas públicas cuyos metadatos OpenGraph estén habilitados (`poll_interval_facebook = 1800s` conservador para evitar bloqueos por IP).
- Permite múltiples páginas con credenciales independientes mediante `credentials_ref` (`FB_MAIN_PAGE_ID` / `FB_MAIN_ACCESS_TOKEN`, `FB_<REF>_PAGE_ID` / `FB_<REF>_ACCESS_TOKEN`).

---

## 4. Estado de Verificación Empírica
- Verificado mediante mocks deterministas (`respx`) para Nivel A y Nivel B bilingüe en `tests/unit/collectors/test_facebook.py`.
- Verificado empíricamente en vivo contra `https://www.facebook.com/raupulus/` con `curl_cffi` (`200 OK`: extracción de `590 followers` desde `og:description`).

---
> Creado: 2026-10-29 · Última revisión: 2026-10-29
