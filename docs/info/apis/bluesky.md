# Integración API Externa: Bluesky AT Protocol (`BlueskyCollector`)

Integración con la API pública abierta de Bluesky (`https://public.api.bsky.app/xrpc`).

---

## 1. Endpoints Utilizados
1. **Batch de Perfiles (hasta 25 cuentas por llamada):**
   - `GET https://public.api.bsky.app/xrpc/app.bsky.actor.getProfiles?actors={h1}&actors={h2}`
2. **Feed de Autor (último post original):**
   - `GET https://public.api.bsky.app/xrpc/app.bsky.feed.getAuthorFeed?actor={handle}&limit=5&filter=posts_no_replies`

---

## 2. Mapeo de Campos
- `followersCount` $\rightarrow$ `followers_total`.
- `postsCount` $\rightarrow$ `posts_total`.
- Primer ítem de `feed` donde `reason is None` (descarta reposts ajenos):
  - `post.uri` $\rightarrow$ `latest_post.post_id`.
  - `post.likeCount` $\rightarrow$ `latest_post.likes`.
  - `post.replyCount` $\rightarrow$ `latest_post.comments`.
  - `post.repostCount + post.quoteCount` $\rightarrow$ `latest_post.shares`.
  - `latest_post.views = None` (AT Protocol no expone contador público de impresiones).

---

## 3. Autenticación y Cuotas
- No requiere ninguna clave ni token de autenticación.

---

## 4. Estado de Verificación Empírica
- Contrato y filtrado de reposts verificados mediante mocks HTTP deterministas (`respx`) en `tests/unit/collectors/test_bluesky.py`.
- Peticiones en vivo contra `public.api.bsky.app`: `⚠️ sin verificar` en este entorno de desarrollo local.

---
> Creado: 2026-10-28 · Última revisión: 2026-10-28
