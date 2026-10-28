# Plantilla de Módulo: [Nombre del Módulo]

> **Guía de uso:** Esta plantilla es de uso obligatorio al crear un nuevo módulo en el proyecto. 
> Todos los apartados son obligatorios. Lo que no se pueda verificar directamente contra código se marca como `⚠️ sin verificar`.

---

## 1. Qué hace y qué NO hace

### 1.1. Qué hace
- [Descripción clara de las responsabilidades directas que asume el módulo]

### 1.2. Qué NO hace
- [Límites explícitos de responsabilidad para evitar acoplamientos o tareas asumidas por otros módulos]

---

## 2. Modelo de datos
- [Estructuras de datos, modelos Pydantic, esquemas o tipos que manipula o expone este módulo]
- [Campos clave, tipos y validaciones relevantes]

---

## 3. Flujos principales
- [Paso a paso de las operaciones centrales del módulo]
- [Diagrama textual o flujo secuencial de llamadas y transformaciones]

---

## 4. Puntos de entrada (Auth, permisos y límites)
- [Funciones públicas, clases, endpoints o métodos que exponen la funcionalidad]
- [Autenticación requerida / permisos / rate limits o restricciones de concurrencia]

---

## 5. Dependencias en ambos sentidos
- **Depende de:** [Módulos internos y librerías externas que este módulo importa/consume]
- **Consumido por:** [Módulos o servicios que dependen directamente de este módulo]

---

## 6. Configuración
| Variable / Parámetro | Tipo | Valor por defecto | Efecto / Comportamiento |
|---|---|---|---|
| `PARAM_NAME` | `str` | `"default"` | Descripción de cómo afecta al funcionamiento |

---

## 7. Trampas conocidas y consideraciones de diseño
- [Comportamientos no intuitivos, casos esquina (*edge cases*), quirks de librerías o plataformas externas]
- [Cómo evitar romper el módulo por desconocimiento]

---

## 8. Tests que lo cubren
- [Ruta a los archivos de test unitarios o de integración que verifican este módulo]
- [Comando exacto para ejecutarlos]

---

## 9. Pendiente real
- [Deuda técnica conocida, mejoras pendientes o elementos marcados como `⚠️ sin verificar`]

---
> Creado: 2026-10-28 · Última revisión: 2026-10-28
