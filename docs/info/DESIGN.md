# Guía de Diseño Visual y Sistema de Telemetría (`stats.raupulus.dev`)

Especificación visual definitiva para la web pública (`public/`) y clientes de escritorio. Combina la **paleta azul oscura profesional de `https://raupulus.dev/`** con una estética de **telemetría futurista sobria**: bordes luminosos sutiles, haces de luz diagonal especular, píldoras de ámbito y tarjetas de selección de perfil con indicador `✓ ACTIVO`.

---

## 1. Dirección Estética («Deep-Space Blue Cyber-Telemetry»)

1. **Sobriedad técnica y profesional:** Sin efectos estridentes ni neones saturados; predominan los azules abisales (`#050f1c`, `#091421`, `#121c2a`) con acentos en azul acero luminoso (`#a3c9ff`, `#3272b8`) y cian técnico (`#4cd6ff`, `#007a96`).
2. **Superficies con haz de luz diagonal especular:** Los paneles y tablas de telemetría emplean un gradiente diagonal sutil (`125deg`) que simula un reflejo de cristal técnico sobre fondo marino profundo, enmarcado por un borde de `1px` con brillo cian/azul controlado.
3. **Jerarquía de lectura instantánea («Glanceable UI»):**
   - Cabecera superior con punto luminoso de estado de conexión WebSocket antes de «Telemetría y Estadísticas de Proyectos» y píldoras de filtro de categoría.
   - Bloque **«ÁMBITO DE SUPERVISIÓN»** con todos los perfiles seleccionados por defecto (`✓ ACTIVO`) y píldora derecha `Contexto activo: <Perfiles>`.
   - Bloques modulares diferenciados: **Resumen de Redes Sociales y Forjas Git** (con iconos `.webp` oficiales 64x64@2x y pie con botón de copiado al portapapeles + enlace externo), **Cotización Cripto Spot Global (USD / EUR)**, **Keycounter (Acumulado Histórico por Perfil, oculto automáticamente cuando el perfil seleccionado no tiene cuenta)** y **Tabla de Especificaciones / Flujo de Telemetría**.
   - Pie de página con la marca de tiempo de **Última actualización** formateada en la zona horaria local del navegador.

---

## 2. Paleta de Color Oficial (Extraída de `raupulus.dev`)

Todos los clientes web (`public/css/styles.css`) deben declarar y utilizar exactamente estos tokens CSS en `:root`:

```css
:root {
  color-scheme: dark;

  /* Fondos y superficies (Jerarquía de profundidad azul marino) */
  --color-surface-container-lowest: #050f1c;
  --color-background: #091421;
  --color-surface: #091421;
  --color-surface-dim: #091421;
  --color-surface-container-low: #121c2a;
  --color-surface-container: #16202e;
  --color-surface-container-high: #212b39;
  --color-surface-container-highest: #2b3544;
  --color-surface-bright: #303a48;

  /* Acentos primarios (Azul profesional raupulus.dev) */
  --color-primary: #a3c9ff;
  --color-primary-container: #3272b8;
  --color-on-primary: #00315c;
  --color-on-primary-container: #f8f9ff;

  /* Acentos terciarios (Cian de telemetría / foco activo) */
  --color-tertiary: #4cd6ff;
  --color-tertiary-container: #007a96;
  --color-on-tertiary: #003543;
  --color-on-tertiary-container: #f5fcff;

  /* Acentos secundarios (Ámbar cálido para avisos / stale) */
  --color-secondary: #ffb691;
  --color-secondary-container: #ea6b15;
  --color-on-secondary: #552000;

  /* Texto y bordes */
  --color-on-surface: #d9e3f6;
  --color-on-surface-variant: #c1c7d2;
  --color-outline: #9ea8b8;
  --color-outline-variant: #414751;

  /* Estados semánticos */
  --color-success: #38e59d;
  --color-warning: #ffb691;
  --color-error: #ffb4ab;

  /* Efectos de iluminación y bordes futuristas */
  --border-subtle: rgba(163, 201, 255, 0.16);
  --border-glow-active: rgba(76, 214, 255, 0.58);
  --shadow-glow-active: 0 0 24px -4px rgba(76, 214, 255, 0.26),
                        inset 0 1px 0 0 rgba(163, 201, 255, 0.22);
  --gradient-diagonal-beam: linear-gradient(
    125deg,
    rgba(18, 28, 42, 0.94) 0%,
    rgba(22, 32, 46, 0.92) 38%,
    rgba(50, 114, 184, 0.18) 54%,
    rgba(18, 28, 42, 0.96) 72%,
    rgba(5, 15, 28, 0.98) 100%
  );
}
```

---

## 3. Tipografía y Escala Fluida

- **Títulos, cabeceras de sección y etiquetas técnicas (`--font-headline`):**
  `'Space Grotesk', system-ui, -apple-system, sans-serif` — tracking amplio en subtítulos de sección (`letter-spacing: 0.08em`, `text-transform: uppercase`).
- **Cuerpo de texto y descripciones (`--font-body`):**
  `'Plus Jakarta Sans', system-ui, -apple-system, sans-serif`.
- **Contadores numéricos, precios cripto, deltas y píldoras de código (`--font-mono`):**
  `'JetBrains Mono', ui-monospace, SFMono-Regular, Menlo, monospace` con `font-variant-numeric: tabular-nums` obligatorio para evitar desplazamientos horizontales al actualizar métricas en vivo.
- **Escala tipográfica fluida (`clamp()`):**
  - Título principal: `clamp(1.35rem, 2.2vw, 1.85rem)`
  - Contador principal de tarjeta: `clamp(1.6rem, 2.8vw, 2.25rem)`
  - Contador gigante Keycounter / Cripto: `clamp(1.75rem, 3vw, 2.5rem)`

---

## 4. Patrones Visuales de Referencia

### 4.1. Sección «ÁMBITO DE SUPERVISIÓN» y Tarjetas de Perfil
- **Cabecera de sección dividida:**
  - Izquierda: Título en mayúsculas `ÁMBITO DE SUPERVISIÓN` con icono/acento azul y subtítulo descriptivo.
  - Derecha: Píldora oscura con borde luminoso `Contexto activo: <Nombre del Perfil>`.
- **Tarjetas de Selección de Perfil (`ProfileSelectorCard`):**
  - Disposición horizontal en cuadrícula adaptable (`grid-template-columns: repeat(auto-fit, minmax(min(100%, 280px), 1fr))`).
  - **Estado activo:** Borde luminoso `--border-glow-active`, sombra `--shadow-glow-active`, avatar circular con iniciales/icono a la izquierda, título del perfil y subtítulo en el centro, contador de plataformas/cuentas en píldora superior derecha (`N redes`) e insignia inferior derecha `✓ ACTIVO` en cian/azul brillante.
  - Permiten conmutar entre **«Todos los perfiles (Global)»** o cualquiera de los perfiles públicos configurados (`raupulus`, `proyecto_secundario`, etc.).

### 4.2. Tabla / Panel de Telemetría con Haz de Luz Diagonal
- Contenedor con fondo `--gradient-diagonal-beam`, borde `1px solid var(--border-subtle)`, esquinas redondeadas (`14px`) y filas separadas por líneas horizontales de `1px solid rgba(163, 201, 255, 0.1)`.
- Columna izquierda con etiqueta en negrita (`--color-on-surface`) y columna derecha con valores técnicos encapsulados en píldoras monoespaciadas (`background: rgba(5, 15, 28, 0.75); border: 1px solid rgba(76, 214, 255, 0.24); color: var(--color-tertiary)`).

### 4.3. Reglas de Exposición en la Web Pública (`public/`)
- **Identidad Visual (`favicon.svg`, `logo.svg`, `icon-192.png`/`webp`, `og-preview.png`/`webp` y assets de repositorio):**
  - Emblema isométrico de nodo hexagonal con barras de espectro y anillos concéntricos en los tonos oficiales `#050f1c`, `#091421`, `#3272b8`, `#a3c9ff` y `#4cd6ff`.
  - `public/og-preview.png` y `public/og-preview.webp` (`1280x640` px para tarjetas OpenGraph y Twitter/X `summary_large_image`).
  - `public/icon-192.png` y `public/icon-192.webp` (`192x192` px para `site.webmanifest` y `apple-touch-icon`).
  - `docs/images/gitlab-avatar-192x192.png` (avatar 192x192 px con transparencia para GitLab).
  - `docs/images/github-social-preview-1280x640.png` (social preview card 1280x640 px para GitHub).
  - `docs/images/banner.webp` (banner ligero optimizado WebP para `README.md`).
- **SEO Técnico, W3C, Accesibilidad WCAG AA/AAA y Rendimiento (Lighthouse 100/100):**
  - Metadatos completos en `public/index.html` (canonical, `robots`, OpenGraph `og:*`, Twitter/X Cards `twitter:*`, `site.webmanifest`, `sitemap.xml` enlazado desde `robots.txt` y datos estructurados Schema.org JSON-LD para `WebSite`, `WebApplication` y `Person`).
  - Enlace de salto para teclado (`.skip-link.visually-hidden` hacia `<main id="main-content" tabindex="-1">`), contornos `:focus-visible` de alto contraste (`3px solid var(--color-tertiary)`), regiones semánticas sin `aria-labelledby` redundante en `<section>`, e iconos decorativos con `alt=""` junto a encabezados `<h3>` para evitar anuncios duplicados en lectores de pantalla.
  - Priorización de imagen LCP (`fetchpriority="high"` en `/logo.svg`), `loading="lazy"` en iconos dinámicos de plataforma, diferimiento de pintado fuera de pantalla con `content-visibility: auto` y `contain-intrinsic-size: auto none auto 320px` (`.deferred-section`), y altura mínima reservada en rejillas dinámicas para mantener `CLS = 0`.
- **Redes Sociales, Forjas Git y Streaming:** Muestra el icono `.webp` optimizado (`32x32` CSS / `64x64` Retina lossless en `public/images/platforms/<plataforma>.webp`) en la cabecera de cada tarjeta, seguidores/suscriptores totales, $\Delta_{24h}$, publicaciones/repositorios totales, estrellas y forks acumulados (`GitHub`, `GitLab`), estado de emisión en directo y espectadores (`Twitch`), suscriptores y vistas del último mensaje (`Telegram`), seguidores/Me gusta (`Facebook`), visualizaciones y pie de tarjeta con botón de copiado rápido al portapapeles y enlace directo (`target="_blank"`) a cada cuenta/canal.
- **Criptomonedas Globales (`BTC`, `ADA`):** Configuradas a nivel global (independientes del perfil seleccionado). Muestra icono `.webp` (`btc.webp`, `ada.webp`), cotización spot en vivo tanto en **USD (`$`)** como en **EUR (`€`)**, variación porcentual 24h y rango máximo/mínimo 24h.
- **Keycounter (Privacidad de Actividad Reciente y Ocultación Condicional):** Asociado a cada perfil. Si los perfiles seleccionados no tienen cuenta de Keycounter configurada, la sección completa (`#section-keycounter`) y su píldora de filtro (`#filter-pill-keycounter`) se ocultan automáticamente. Cuando está presente, en la web pública se muestran **única y exclusivamente los totales históricos acumulados** (`pulsations_total` y `clicks_total`). Nunca se renderizan ni reciben contadores de «hoy» ni de «última hora».
- **Seguridad DOM:** Prohibido el uso de `innerHTML`, `outerHTML` o `document.write`. Toda actualización del DOM se realiza con `document.createElement` y `textContent`.

---
> Creado: 2026-10-28 · Última revisión: 2026-10-29
