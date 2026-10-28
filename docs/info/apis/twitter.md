# Integración API Externa: Twitter / X (`TwitterCollector`)

Estrategia de doble nivel desatendida para Twitter/X: Nivel A (Syndication API pública sin credenciales) y Nivel B opcional (GraphQL con cookies de sesión Read-Only de larga duración).

---

## 1. Endpoints Utilizados
1. **Nivel A — Syndication API (Sin credenciales):**
   - Seguidores en batch: `GET https://cdn.syndication.twimg.com/widgets/followbutton/info.json?screen_names={handles}`
   - Timeline de perfil (`__NEXT_DATA__`): `GET https://syndication.twitter.com/srv/timeline-profile/screen-name/{handle}`
   - Detalle de tweet (fallback de vistas): `GET https://cdn.syndication.twimg.com/tweet-result?id={tweet_id}&token=x`
2. **Nivel B — GraphQL Read-Only (Opcional si existen cookies en `.env`):**
   - `GET https://x.com/i/api/graphql/UserByScreenName`
   - `GET https://x.com/i/api/graphql/UserTweets`
   - Si Nivel B devuelve `401`/`403`/`429`, degrada transparente y automáticamente a Nivel A.

---

## 2. Mapeo de Campos
- `followers_count` $\rightarrow$ `followers_total`.
- `statuses_count` $\rightarrow$ `posts_total`.
- Último tweet propio (ordenado por `snowflake id` descendente para ignorar tweets fijados antiguos):
  - `ext_views.count` / `views.count` $\rightarrow$ `latest_post.views`.
  - `favorite_count` $\rightarrow$ `latest_post.likes`.
  - `reply_count` $\rightarrow$ `latest_post.comments`.
  - `retweet_count + quote_count` $\rightarrow$ `latest_post.shares`.

---
> Creado: 2026-10-28 · Última revisión: 2026-10-28
