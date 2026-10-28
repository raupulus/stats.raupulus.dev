# Integración API Externa: TikTok (`TikTokCollector`)

Extracción SSR desde hidratación `__UNIVERSAL_DATA_FOR_REHYDRATION__` con huella TLS (`curl_cffi`) y soporte opcional para TikTok Display API v2 con rotación automática de tokens en SQLite.

---

## 1. Mecanismos Utilizados
1. **Hidratación SSR (Sin credenciales):**
   - `GET https://www.tiktok.com/@{handle}` leyendo `<script id="__UNIVERSAL_DATA_FOR_REHYDRATION__" type="application/json">`.
   - Extrae `__DEFAULT_SCOPE__["webapp.user-detail"]["userInfo"]["stats"]` (`followerCount`, `videoCount`) y el primer elemento de `itemList` (`playCount`, `diggCount`, `commentCount`, `shareCount`).
2. **Display API v2 con Auto-Refresh (Opcional):**
   - Si existe un token en la tabla `auth_tokens` de SQLite (`provider='tiktok'`) y ha expirado, lo renueva automáticamente contra `POST https://open.tiktokapis.com/v2/oauth/token/` guardando el nuevo par `(access_token, refresh_token)` en SQLite.
   - Consulta `POST https://open.tiktokapis.com/v2/video/list/?fields=id,create_time,view_count,like_count,comment_count,share_count` (`max_count=1`).

---

## 2. Estado de Verificación Empírica
- Extracción de `__UNIVERSAL_DATA_FOR_REHYDRATION__`, transporte `curl_cffi` (`impersonate="chrome124"`) y rotación OAuth2 en SQLite (`auth_tokens`) verificados mediante tests unitarios en `tests/unit/collectors/test_tiktok.py`.
- Extracción SSR en vivo frente a desafíos anti-bot de `www.tiktok.com` y flujo real contra `open.tiktokapis.com`: `⚠️ sin verificar` en este entorno de desarrollo local.

---
> Creado: 2026-10-28 · Última revisión: 2026-10-28
