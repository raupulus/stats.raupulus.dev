# Integración API Externa: Twitch Helix API + Public GQL (`TwitchCollector`)

Arquitectura dual de dos niveles para canales de Twitch con detección de estado en directo (`is_live`) y espectadores simultáneos (`live_viewers`).

---

## 1. Endpoints Utilizados
### Nivel A — Twitch Helix API Oficial (Opcional, si `TWITCH_CLIENT_ID` y `TWITCH_CLIENT_SECRET` están configurados)
1. **Obtención y auto-renovación de App Access Token (`client_credentials`):**
   - `POST https://id.twitch.tv/oauth2/token` (credenciales enviadas exclusivamente en cuerpo `application/x-www-form-urlencoded`, jamás en query string).
2. **Datos del Canal, Seguidores, Directo Activo y Último VOD:**
   - `GET https://api.twitch.tv/helix/users?login={handle}`
   - `GET https://api.twitch.tv/helix/channels/followers?broadcaster_id={id}&first=1`
   - `GET https://api.twitch.tv/helix/streams?user_id={id}`
   - `GET https://api.twitch.tv/helix/videos?user_id={id}&first=1`
   *(Cabeceras `Client-Id` y `Authorization: Bearer <app_token>`).*

### Nivel B — Fallback Público Twitch GraphQL (Sin credenciales)
- `POST https://gql.twitch.tv/gql` (cabecera pública `Client-Id: kimne78kx3ncx6brgo4mv6wki5h1ko`) consultando `user(login) { followers { totalCount } stream { id viewersCount createdAt } videos(first: 1) { totalCount edges { node { id viewCount publishedAt } } } }`.

---

## 2. Mapeo de Campos
- `total` (Helix) o `followers.totalCount` (GQL) $\rightarrow$ `followers_total`.
- `videos.totalCount` (GQL) $\rightarrow$ `posts_total` (total de vídeos/VODs publicados).
- Presencia de `stream` activo $\rightarrow$ `is_live` (`true` / `false`).
- `viewer_count` (Helix) o `stream.viewersCount` (GQL) $\rightarrow$ `live_viewers` (`0` si está offline).
- Último VOD (o stream activo si no hay VODs) $\rightarrow$ `latest_post` (`post_id`, `url`, `published_at`, `views`).

---

## 3. Autenticación y Resiliencia
- Funciona sin configuración adicional desde el primer arranque gracias al Nivel B (GQL público).
- Si se configuran `TWITCH_CLIENT_ID` y `TWITCH_CLIENT_SECRET`, prioriza la API oficial Helix cacheando en memoria el token OAuth2 hasta 60 segundos antes de su expiración, con fallback transparente al Nivel B ante cualquier incidencia.

---

## 4. Estado de Verificación Empírica
- Verificado mediante mocks deterministas (`respx`) para Nivel A (Helix online) y Nivel B (GQL offline) en `tests/unit/collectors/test_twitch.py`.
- Verificado empíricamente en vivo contra `https://gql.twitch.tv/gql` para el canal `raupulus` (`200 OK`: `followers.totalCount`, `stream` y `videos.totalCount`).

---
> Creado: 2026-10-29 · Última revisión: 2026-10-29
