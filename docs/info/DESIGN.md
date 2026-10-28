# Guía de Diseño Visual y Experiencia de Usuario (Dashboard de Escritorio)

Criterios de diseño, maquetación y jerarquía visual para clientes y pantallas de escritorio que consuman esta API y WebSockets.

---

## 1. Principios de Visualización («Glanceable UI»)

El objetivo principal de la interfaz de cliente es mostrar estadísticas en una pantalla secundaria o monitor de escritorio dedicada. Por tanto:
1. **Lectura instantánea de un vistazo:** Las métricas más relevantes (seguidores, visitas último día y última hora) deben ser legibles a distancia de trabajo (1–2 metros).
2. **Alto contraste y tema oscuro preferente:** Fondo oscuro neutro para evitar fatiga visual durante jornadas prolongadas en el escritorio.
3. **Indicadores de estado sutiles pero inequívocos:**
   - Verde: Conexión WebSocket activa / Colectores en estado `healthy`.
   - Ámbar/Naranja: Modo `stale` (mostrando último dato conocido con indicador discreto de antigüedad).
   - Rojo: Error de conexión con el backend local.

---

## 2. Tipografía y Números

- **Fuente monoespaciada para valores numéricos:** Se recomienda el uso de fuentes con cifras tabulares o monoespaciadas (`JetBrains Mono`, `Fira Code`, `Inter` con `font-feature-settings: "tnum"`) para evitar oscilaciones o saltos de layout cuando los contadores cambian.
- **Formateo numérico:**
  - Valores compactos en badges secundarios (ej. `14.2K`, `1.2M`).
  - Cifras exactas formateadas con separador de miles en vistas ampliadas (ej. `14,215`).

---

## 3. Disposición y Layout de Perfiles

- **Bloques por Perfil:** Cada perfil (`raupulus`, etc.) se organiza en paneles o cuadrículas independientes.
- **Micro-indicadores de variación ($\Delta$):**
  - $\Delta_{1h}$ y $\Delta_{24h}$ destacados junto al contador acumulado.
  - Verde con signo `+` para incrementos netos.
  - Gris neutro para variaciones `0`.

---
> Creado: 2026-10-28 · Última revisión: 2026-10-28
