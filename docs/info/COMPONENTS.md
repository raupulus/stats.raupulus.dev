# Catálogo de Componentes de Interfaz (`public/`)

Definición estructural, visual y de accesibilidad de los componentes implementados en el dashboard público (`public/`) sobre el flujo en tiempo real `/ws/public`.

---

## 1. Componentes de Navegación y Contexto

### 1.1. `TopTelemetryBar`
- **Propósito:** Cabecera superior fija/estática que identifica el nodo de telemetría (`stats.raupulus.dev`), los filtros rápidos de plataforma y el indicador de estado del stream WebSocket (`/ws/public`).
- **Elementos:**
  - Insignia de identidad con pulso luminoso azul/cian.
  - Píldoras de filtro rápido por categoría (`Todas`, `Redes Sociales`, `Cripto Spot`, `Keycounter`).
  - `ConnectionStatusIndicator`: píldora con punto de estado (`CONECTADO EN VIVO`, `RECONECTANDO…`, `SIN CONEXIÓN`) y reloj de última sincronización UTC.

### 1.2. `SupervisionScopeSection` y `ProfileSelectorCard`
- **Propósito:** Permite visualizar y seleccionar el ámbito de supervisión activo (vista agregada global o un perfil concreto como `raupulus` o `proyecto_secundario`).
- **Estructura visual (inspirada en el diseño de referencia):**
  - Cabecera con título `ÁMBITO DE SUPERVISIÓN` a la izquierda y píldora `Contexto activo: <Nombre>` a la derecha.
  - Cuadrícula de tarjetas interactivas (`<button type="button" class="profile-selector-card" aria-pressed="true|false">`):
    - Avatar circular con iniciales/icono del perfil y halo azul.
    - Nombre del perfil y descripción secundaria.
    - Píldora superior derecha con el número de redes/cuentas activas (`9 cuentas`).
    - Píldora inferior derecha con el estado de selección: `✓ ACTIVO` (con borde y texto `--color-tertiary` `#4cd6ff`) cuando está seleccionado, o `SELECCIONAR` en estado inactivo.

---

## 2. Componentes de Métricas en Tiempo Real

### 2.1. `SocialPlatformCard` (`StatCard`)
- **Propósito:** Presenta las métricas agregadas y el desglose por cuenta de cada red social pública (`YouTube`, `Twitter/X`, `Instagram`, `Bluesky`, `Mastodon`, `TikTok`, `LinkedIn`).
- **Elementos visuales:**
  - Cabecera con icono vectorial de la red social, nombre de plataforma, píldora de número de canales y punto de estado (`healthy` / `stale`).
  - Métrica principal en tipografía monoespaciada (`followers_total`) acompañada de `MetricDeltaBadge` ($\Delta_{24h}$).
  - Métricas secundarias en rejilla compacta: `Publicaciones` (`posts_total`), `Vistas Totales` (`views_total`, si aplica), `Vistas 24h` ($\Delta_{24h}$) y `Vistas 1h` ($\Delta_{1h}$).
  - Lista desglosada de cuentas/canales del perfil (ej. canal principal y canal secundario de YouTube) con sus respectivos contadores y enlace seguro (`rel="noopener noreferrer"`) o identificador `@handle`.

### 2.2. `CryptoSpotCard`
- **Propósito:** Muestra la cotización spot en tiempo real de cada criptomoneda configurada (`BTC`, `ADA`) en **doble divisa (USD y EUR)**.
- **Elementos visuales:**
  - Cabecera con símbolo (`BTC`, `ADA`), nombre (`Bitcoin`, `Cardano`) y badge de variación porcentual 24h (`+0.62%` en verde `--color-success` o rojo `--color-error`).
  - Doble bloque de precio con cifras tabulares:
    - **Precio Spot USD (`$`)** y variación 24h en dólares.
    - **Precio Spot EUR (`€`)** y variación 24h en euros.
  - Pie técnico con rango 24h (`Máx 24h` / `Mín 24h` en USD y EUR).

### 2.3. `KeycounterTotalsPanel`
- **Propósito:** Muestra los contadores históricos acumulados de periféricos (`Keycounter`) permitidos en el canal público.
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
> Creado: 2026-10-28 · Última revisión: 2026-10-28
