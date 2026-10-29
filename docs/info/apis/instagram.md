# Integración API Externa: Instagram (`InstagramCollector`)

Estrategia de doble nivel para Instagram: Nivel A (Meta Graph API v21.0 con System User Token permanente) y Nivel B (Fallback Web Profile API con impersonación TLS `chrome124`).

---

## 1. Endpoints Utilizados
1. **Nivel A — Meta Graph API (Con `IG_{REF}_USER_ID` e `IG_{REF}_ACCESS_TOKEN`):**
   - `GET https://graph.facebook.com/v21.0/{ig_user_id}?fields=followers_count,media_count,media.limit(1){id,permalink,timestamp,media_type,like_count,comments_count,play_count}` (cabecera `Authorization: Bearer {TOKEN}`)
2. **Nivel B — Web Profile API y Fallback OpenGraph HTML (Sin token o en fallback de Nivel A):**
   - `GET https://www.instagram.com/api/v1/users/web_profile_info/?username={handle}` (cabecera `x-ig-app-id: 936619743392459`).
   - Fallback de contingencia: `GET https://www.instagram.com/{handle}/` con impersonación TLS `chrome124` vía `curl_cffi` para parsear la etiqueta OpenGraph `<meta property="og:description" content="... Seguidores, ... Siguiendo, ... Publicaciones" />` cuando `web_profile_info` responde `401 require_login: true`.

---

## 2. Mapeo de Campos
- `followers_count` / `edge_followed_by.count` / regex `og:description` $\rightarrow$ `followers_total`.
- `media_count` / `edge_owner_to_timeline_media.count` / regex `og:description` $\rightarrow$ `posts_total`.
- Último post/Reel:
  - `play_count` / `video_view_count` $\rightarrow$ `latest_post.views` (solo en vídeo/Reels; `None` en imagen).
  - `like_count` / `edge_liked_by.count` $\rightarrow$ `latest_post.likes`.
  - `comments_count` / `edge_media_to_comment.count` $\rightarrow$ `latest_post.comments`.

---

## 3. Estado de Verificación Empírica
- Nivel A (Meta Graph API) y fallback a `web_profile_info` verificados mediante tests unitarios en `tests/unit/collectors/test_instagram.py`.
- Fallback OpenGraph HTML con `curl_cffi` (`impersonate="chrome124"`): ✅ **Verificado empíricamente en vivo** contra perfiles reales de Instagram (`@raupulus`) el `2026-10-29`, extrayendo seguidores (`2.570`) y publicaciones (`238`) de forma desatendida.

---
> Creado: 2026-10-28 · Última revisión: 2026-10-29
