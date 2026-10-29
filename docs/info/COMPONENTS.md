# Catálogo de Componentes de Interfaz (`public/`)

Definición estructural, visual y de accesibilidad de los componentes implementados en el dashboard público (`public/`) sobre el flujo en tiempo real `/ws/public`.

---

## 1. Componentes de Navegación y Contexto

### 1.1. `TopTelemetryBar` y `DashboardFooter`
- **Propósito:** Cabecera superior fija/estática que identifica el nodo de telemetría (`stats.raupulus.dev`) y las píldoras de filtro de categoría, complementada por el pie de página con la hora local de última sincronización.
- **Elementos:**
  - En la parte superior de la marca (`.brand-kicker`), el texto `Telemetría y Estadísticas de Proyectos` precedido por el punto indicador de estado WebSocket (`#ws-status-dot`: verde conectado `--color-success`, ámbar conectando `--color-warning`, coral desconectado `--color-error`).
  - Píldoras de filtro rápido por categoría (`Todas las métricas`, `Redes y Forjas`, `Cripto Spot`, y `Keycounter`, esta última oculta automáticamente si el perfil activo no tiene Keycounter asociado).
  - En el `<footer>` (`.dashboard-footer`), el bloque `Última actualización: <code id="last-sync-time">` formateado automáticamente en la zona horaria local del navegador del usuario (`Intl.DateTimeFormat`).

### 1.2. `SupervisionScopeSection` y `ProfileSelectorCard`
- **Propósito:** Permite visualizar y conmutar el ámbito de supervisión activo (todos los perfiles activos simultáneamente por defecto, o filtrado individual por perfil como `raupulus` o `proyecto_secundario`).
- **Estructura visual (inspirada en el diseño de referencia):**
  - Cabecera con título `ÁMBITO DE SUPERVISIÓN` a la izquierda y píldora `Contexto activo: <Perfil 1 + Perfil 2>` a la derecha.
  - Cuadrícula de tarjetas interactivas (`<button type="button" class="profile-selector-card" aria-pressed="true|false">`):
    - Avatar circular con iniciales/icono del perfil y halo azul.
    - Nombre del perfil y descripción secundaria.
    - Píldora superior derecha con el número de redes/cuentas activas (`9 cuentas`).
    - Píldora inferior derecha con el estado de selección: `✓ ACTIVO` (con borde y texto `--color-tertiary` `#4cd6ff`) cuando está activo, o `OCULTO · ACTIVAR` en estado inactivo.

---

## 2. Componentes de Métricas en Tiempo Real

### 2.1. `ProfileSocialGroup` y `SocialPlatformCard` (`StatCard`)
- **Propósito:** Separa y agrupa claramente cada perfil activo en su propio panel contenedor (`.profile-social-group`), mostrando dentro sus tarjetas de plataforma para las 12 redes sociales, forjas y canales soportados (`YouTube`, `Twitch`, `GitHub`, `GitLab`, `Twitter/X`, `Instagram`, `Telegram`, `TikTok`, `Facebook`, `Mastodon`, `Bluesky`, `LinkedIn`).
- **Elementos visuales:**
  - Cabecera del grupo de perfil (`.profile-group-header`) con el nombre del perfil, resumen consolidado de seguidores, estrellas/likes (`★`), visualizaciones y publicaciones/repositorios del perfil, y píldora derecha `@<profile_id> · N plataformas`.
  - Dentro de cada grupo, cuadrícula adaptable (`.profile-group-platforms-grid`) de tarjetas semánticas `<article class="platform-card">` con regiones `<header>`, `.platform-card-content` y `<footer>` y adaptación por `@container`:
    - Cabecera `<header>` con icono oficial `.webp` optimizado (`32x32` CSS / `64x64` Retina lossless en `public/images/platforms/<plataforma>.webp`), nombre de la plataforma y píldora de estado (`N CANAL(ES)`, `● EN DIRECTO · N` pulsante en `Twitch` cuando `is_live === true`, `OFFLINE` o `CACHÉ / STALE`).
    - Métrica principal en tipografía monoespaciada (`followers_total`) acompañada de `MetricDeltaBadge` ($\Delta_{24h}$).
    - Métricas secundarias contextuales en rejilla compacta:
      - `GitHub` / `GitLab`: `Repositorios` / `Proyectos`, `Estrellas Totales` (`★ stars_total`), `Forks Totales` (`forks_total`) y `Último Repo Activo`.
      - `Twitch`: `Estado Stream`, `Espectadores Live` (`live_viewers`), `Vídeos / VODs` y `Vistas Último VOD`.
      - `Telegram`: `Último Mensaje` (`#id`), `Vistas Último Post`, `Vistas 24h` y `Vistas 1h`.
      - `Facebook`: `Me gusta Página` (`stars_total`), `Seguidores 24h`, `Publicaciones` y `Canal`.
      - Resto de plataformas: `Publicaciones` (`posts_total`), `Vistas Totales` (`views_total`), `Vistas 24h` ($\Delta_{24h}$) y `Vistas 1h` ($\Delta_{1h}$).
    - Pie `<footer>` con lista desglosada de cuentas/canales del perfil: cada fila incluye a la izquierda un botón de icono para copiar la URL del canal al portapapeles (`.account-copy-btn.icon` con máscara CSS `--icon` y confirmación visual `.is-copied`), seguido del nombre e identificador enlazados (`<a target="_blank" rel="noopener noreferrer">`) para abrir la red social en una pestaña nueva, y a la derecha la píldora de métrica rápida.
    - Destello luminoso (`.is-flash`) al recibir un evento `metric_update` en vivo y énfasis automático `:has(.is-live-stream)` cuando un canal emite en directo.

### 2.2. `CryptoSpotCard` (Global)
- **Propósito:** Muestra la cotización spot global en tiempo real de cada criptomoneda configurada (`BTC`, `ADA`) en **doble divisa (USD y EUR)** con independencia de qué perfil social esté seleccionado.
- **Elementos visuales:**
  - Cabecera con icono `.webp` optimizado (`btc.webp`, `ada.webp`), nombre (`Bitcoin (BTC)`, `Cardano (ADA)`) y badge de variación porcentual 24h (`+0.62%` en verde `--color-success` o rojo `--color-error`).
  - Doble bloque de precio con cifras tabulares:
    - **Precio Spot USD (`$`)** y variación 24h en dólares.
    - **Precio Spot EUR (`€`)** y variación 24h en euros.
  - Pie técnico con rango 24h (`Máx 24h` / `Mín 24h` en USD y EUR).

### 2.3. `KeycounterTotalsPanel` (Por Perfil con Ocultación Automática)
- **Propósito:** Muestra los contadores históricos acumulados de periféricos (`Keycounter`) asociados a los perfiles activos en el canal público. Si ninguno de los perfiles seleccionados tiene cuenta de Keycounter asociada, toda la sección (`#section-keycounter`) y su píldora de filtro se ocultan automáticamente.
- **Elementos visuales:**
  - Dos tarjetas gemelas con haz de luz diagonal:
    1. **Pulsaciones Totales Históricas (`pulsations_total`):** Cifra monoespaciada de gran formato con etiqueta técnica `TECLADO · ACUMULADO HISTÓRICO`.
    2. **Clics Totales Históricos (`clicks_total`):** Cifra monoespaciada de gran formato con etiqueta técnica `RATÓN · ACUMULADO HISTÓRICO`.
  - Nota explícita de privacidad: el canal público `/ws/public` expone exclusivamente los acumulados totales históricos.

### 2.4. `TelemetrySpecTable`
- **Propósito:** Tabla técnica con estética de cristal oscuro y haz de luz diagonal (`--gradient-diagonal-beam`) que muestra el resumen de cuentas monitorizadas y los últimos eventos `metric_update` recibidos por WebSocket en tiempo real.
- **Elementos visuales:**
  - Filas separadas por divisores sutiles (`1px solid rgba(163, 201, 255, 0.1)`).
  - Etiqueta descriptiva en negrita a la izquierda y píldoras monoespaciadas (`<code>`) a la derecha con los valores y diferenciales ($\Delta$).

---
> Creado: 2026-10-28 · Última revisión: 2026-10-29
