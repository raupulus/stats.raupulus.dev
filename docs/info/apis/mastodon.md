# Integración API Externa: Mastodon REST API v1 (`MastodonCollector`)

Integración con la API REST pública de instancias federadas de Mastodon.

---

## 1. Endpoints Utilizados
1. **Lookup de Cuenta en la Instancia:**
   - `GET https://{instance}/api/v1/accounts/lookup?acct={handle}`
2. **Último Toot Original Publicado:**
   - `GET https://{instance}/api/v1/accounts/{account_id}/statuses?limit=1&exclude_replies=true&exclude_reblogs=true`

---

## 2. Mapeo de Campos
- `followers_count` $\rightarrow$ `followers_total`.
- `statuses_count` $\rightarrow$ `posts_total`.
- Primer elemento de `statuses`:
  - `id` $\rightarrow$ `latest_post.post_id`.
  - `url` $\rightarrow$ `latest_post.url`.
  - `created_at` $\rightarrow$ `latest_post.published_at`.
  - `favourites_count` $\rightarrow$ `latest_post.likes`.
  - `replies_count` $\rightarrow$ `latest_post.comments`.
  - `reblogs_count` $\rightarrow$ `latest_post.shares`.

---

## 3. Autenticación y Resiliencia
- No requiere autenticación para cuentas públicas.
- Cada cuenta se recolecta de forma aislada: la caída de una instancia federada no afecta al resto de instancias configuradas.

---
> Creado: 2026-10-28 · Última revisión: 2026-10-28
