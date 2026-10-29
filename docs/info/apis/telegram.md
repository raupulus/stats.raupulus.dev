# Integración API Externa: Telegram Public Channel Preview (`TelegramCollector`)

Extracción pasiva de métricas de canales públicos de Telegram sin utilizar la Bot API (evitando exponer tokens de bot en URLs ni añadir bots como administradores del canal).

---

## 1. Endpoints Utilizados
1. **Vista Previa Pública de Canal:**
   - `GET https://t.me/s/{handle}`
2. **Tarjeta Pública de Respaldo (si `/s/` no expone bloque de contadores):**
   - `GET https://t.me/{handle}`

---

## 2. Mapeo de Campos
- `<div class="tgme_channel_info_counter">` (`subscribers` / `members`) o `<div class="tgme_page_extra">` $\rightarrow$ `followers_total` (suscriptores del canal).
- Mayor identificador secuencial `data-post="{handle}/{post_id}"` $\rightarrow$ `posts_total` y `latest_post.post_id`.
- `https://t.me/{handle}/{post_id}` $\rightarrow$ `latest_post.url`.
- `<span class="tgme_widget_message_views">` del último mensaje $\rightarrow$ `latest_post.views` y `views_total`.
- `<time datetime="...">` del último mensaje $\rightarrow$ `latest_post.published_at`.

---

## 3. Autenticación y Seguridad
- **Cero credenciales:** No emplea tokens ni claves. Cumple estrictamente la política de cero credenciales en URLs.
- Acepta handles tanto limpios (`raupulus_diffusion`) como con `@` o URL completa (`https://t.me/raupulus_diffusion`).

---

## 4. Estado de Verificación Empírica
- Verificado mediante mocks deterministas (`respx`) en `tests/unit/collectors/test_telegram.py`.
- Verificado empíricamente en vivo contra `https://t.me/s/raupulus_diffusion` (`200 OK`: suscriptores, ID del último mensaje y visualizaciones).

---
> Creado: 2026-10-29 · Última revisión: 2026-10-29
