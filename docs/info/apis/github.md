# Integración API Externa: GitHub REST API v3 (`GitHubCollector`)

Integración con la API REST oficial v3 de GitHub (`2022-11-28`) para perfiles personales y organizaciones.

---

## 1. Endpoints Utilizados
1. **Perfil de Usuario u Organización:**
   - `GET https://api.github.com/users/{handle}`
2. **Listado Paginado de Repositorios Públicos Propios:**
   - `GET https://api.github.com/users/{handle}/repos?per_page=100&type=owner&sort=pushed&direction=desc&page={1..N}` (límite de seguridad `MAX_REPO_PAGES = 20`).

---

## 2. Mapeo de Campos
- `followers` $\rightarrow$ `followers_total`.
- `public_repos` $\rightarrow$ `posts_total` (total de repositorios públicos).
- $\sum \text{stargazers\_count}$ en todos los repositorios públicos $\rightarrow$ `stars_total` ("me gusta" / estrellas acumuladas).
- $\sum \text{forks\_count}$ en todos los repositorios públicos $\rightarrow$ `forks_total`.
- Primer repositorio ordenado por `pushed` descendente:
  - `id` $\rightarrow$ `latest_post.post_id`.
  - `html_url` $\rightarrow$ `latest_post.url`.
  - `pushed_at` $\rightarrow$ `latest_post.published_at`.
  - `stargazers_count` $\rightarrow$ `latest_post.likes`.
  - `open_issues_count` $\rightarrow$ `latest_post.comments`.
  - `forks_count` $\rightarrow$ `latest_post.shares`.

---

## 3. Autenticación y Seguridad
- **Sin credenciales obligatorias:** Funciona de forma pública (`60 req/h` por IP; con intervalo por defecto de `900s` consume únicamente ~8–12 peticiones/hora).
- **Token opcional (`GITHUB_TOKEN` o `GITHUB_{REF}_TOKEN`):** Si se configura un *Fine-Grained Personal Access Token* de solo lectura sin permisos de escritura, se inyecta exclusivamente en cabecera `Authorization: Bearer <token>` (jamás en query string), elevando la cuota a `5.000 req/h`.
- Optimización de cuota: la paginación se detiene automáticamente en cuanto `counted_repos >= public_repos` o una página devuelve menos de `100` elementos.

---

## 4. Estado de Verificación Empírica
- Verificado mediante mocks deterministas (`respx`) en `tests/unit/collectors/test_github.py`.
- Verificado empíricamente en vivo contra `https://api.github.com/users/raupulus` (`200 OK`: seguidores, repositorios públicos, suma de `stargazers_count` y `forks_count`).

---
> Creado: 2026-10-29 · Última revisión: 2026-10-29
