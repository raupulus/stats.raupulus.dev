# Integración API Externa: GitLab REST API v4 + Public XHR (`GitLabCollector`)

Integración multi-instancia compatible tanto con `gitlab.com` como con instancias GitLab autoalojadas (`instance`).

---

## 1. Endpoints Utilizados
1. **Resolución de ID Numérico de Usuario:**
   - `GET https://{instance}/api/v4/users?username={handle}`
2. **Conteo de Seguidores (Doble Nivel):**
   - **Nivel A (REST API v4):** `GET https://{instance}/api/v4/users/{user_id}` (`followers`). Funciona directamente cuando se configura `GITLAB_TOKEN` (`read_api`) o en instancias autoalojadas con perfil detallado público.
   - **Nivel B (Fallback Público XHR en `gitlab.com` sin token):** En `gitlab.com`, `/api/v4/users/{user_id}` devuelve `HTTP 403` a peticiones anónimas. El colector conmuta transparentemente a `GET https://{instance}/users/{handle}/followers.json?page={1..N}` (`X-Requested-With: XMLHttpRequest`), contabilizando las tarjetas `gl-card` renderizadas sin requerir credenciales.
3. **Listado Paginado de Proyectos Públicos:**
   - `GET https://{instance}/api/v4/users/{user_id}/projects?per_page=100&page={1..N}&order_by=last_activity_at&sort=desc`

---

## 2. Mapeo de Campos
- `followers` (Nivel A) o conteo de tarjetas `followers.json` (Nivel B) $\rightarrow$ `followers_total`.
- Cabecera `x-total` de `/projects` (o conteo total paginado) $\rightarrow$ `posts_total` (total de proyectos/repositorios públicos).
- $\sum \text{star\_count}$ en todos los proyectos públicos $\rightarrow$ `stars_total`.
- $\sum \text{forks\_count}$ en todos los proyectos públicos $\rightarrow$ `forks_total`.
- Proyecto con actividad más reciente (`projects[0]`):
  - `id` $\rightarrow$ `latest_post.post_id`.
  - `web_url` $\rightarrow$ `latest_post.url`.
  - `last_activity_at` $\rightarrow$ `latest_post.published_at`.
  - `star_count` $\rightarrow$ `latest_post.likes`.
  - `open_issues_count` $\rightarrow$ `latest_post.comments`.
  - `forks_count` $\rightarrow$ `latest_post.shares`.

---

## 3. Autenticación y Seguridad
- **Sin credenciales obligatorias:** Funciona sin token en `gitlab.com` gracias a la combinación de `/api/v4/users?username=`, `/api/v4/users/:id/projects` y el fallback público `followers.json`.
- **Token opcional (`GITLAB_TOKEN` o `GITLAB_{REF}_TOKEN`):** Si se define un token `read_api`, se envía exclusivamente mediante la cabecera HTTP `PRIVATE-TOKEN` (nunca en la URL).

---

## 4. Estado de Verificación Empírica
- Verificado mediante mocks deterministas (`respx`) en `tests/unit/collectors/test_gitlab.py`.
- Verificado empíricamente en vivo contra `gitlab.com` (`raupulus`, `id=512475`: proyectos públicos `x-total`, suma de estrellas, forks y conteo de seguidores por `followers.json`).

---
> Creado: 2026-10-29 · Última revisión: 2026-10-29
