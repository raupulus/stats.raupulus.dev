# Catálogo de Componentes de Interfaz

Definición conceptual y funcional de los componentes de presentación para pantallas y clientes visuales.

---

## 1. Componentes Principales

### 1.1. `StatCard`
- **Propósito:** Muestra la métrica principal de una cuenta o plataforma (ej. Suscriptores de YouTube, Seguidores de Bluesky).
- **Elementos visuales:**
  - Icono de la plataforma.
  - Nombre / etiqueta de la cuenta (`label` o `handle`).
  - Contador principal total acumulado (cifra de gran tamaño).
  - Indicador `MetricDeltaBadge` asociado ($\Delta_{1h}$ y/o $\Delta_{24h}$).
  - Indicador de frescura del dato (`healthy` o `stale`).

### 1.2. `MetricDeltaBadge`
- **Propósito:** Representa la variación en una ventana temporal definida.
- **Variantes:**
  - `delta_1h`: Variación en los últimos 60 minutos.
  - `delta_24h`: Variación en las últimas 24 horas.
- **Estados visuales:**
  - Positivo: Badge verde tenue con texto `+N`.
  - Cero: Badge neutro atenuado `+0`.
  - Negativo: Badge rojo tenue `-N`.

### 1.3. `ConnectionStatusIndicator`
- **Propósito:** Informa visualmente del estado del stream de WebSocket en la pantalla.
- **Estados:**
  - `connected`: Punto verde pulsante o fijo.
  - `reconnecting`: Punto amarillo con animación de espera.
  - `disconnected`: Punto rojo.

### 1.4. `ProfilePanel`
- **Propósito:** Contenedor de nivel superior que agrupa todas las tarjetas de métricas pertenecientes a un mismo perfil lógico (ej. `raupulus`).

---
> Creado: 2026-10-28 · Última revisión: 2026-10-28
