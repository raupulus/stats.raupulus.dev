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
- Cachea en memoria (`_account_id_cache`) el `id` interno resuelto por `accounts/lookup` como respaldo si una cuenta no declaró `account_id` estático en `profiles.yaml`.
- Cada cuenta se recolecta de forma aislada: la caída de una instancia federada no afecta al resto de instancias configuradas.

---

## 4. Estado de Verificación Empírica
- Contrato multi-instancia y aislamiento de errores verificados mediante mocks HTTP deterministas (`respx`) en `tests/unit/collectors/test_mastodon.py`.
- Peticiones en vivo contra instancias federadas reales: `⚠️ sin verificar` en este entorno de desarrollo local.

---
> Creado: 2026-10-28 · Última revisión: 2026-10-28
