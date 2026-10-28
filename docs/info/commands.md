# Inventario de Comandos y Scripts

Registro de comandos CLI, tareas de desarrollo y scripts de automatización verificados en el repositorio.

---

## 1. Comandos de Desarrollo y Verificación

| Comando | Propósito | Variables de entorno requeridas | Salida esperada |
|---|---|---|---|
| `.venv/bin/pytest` | Ejecutar suite completa de tests automatizados. | Ninguna | Código `0` con todos los tests en verde. |
| `.venv/bin/pytest --cov=social_stats` | Ejecutar tests midiendo cobertura de código. | Ninguna | Tabla de cobertura por módulo y código `0`. |
| `.venv/bin/ruff check .` | Analizador estático y linter de código Python. | Ninguna | `All checks passed!` (código `0`). |
| `.venv/bin/mypy src/` | Verificación estricta de tipado estático. | Ninguna | `Success: no issues found` (código `0`). |
| `docker compose up --build -d` | Construir y levantar el contenedor Docker en segundo plano. | Archivo `.env` (basado en `.env.example`) | Contenedor `social-stats-server` en estado `healthy`. |

---

## 2. Convenciones para Nuevos Comandos

Al añadir cualquier script o comando al repositorio:
1. Documentar obligatoriamente en este archivo en el mismo commit.
2. Especificar:
   - **Comando exacto** y sintaxis.
   - **Propósito.**
   - **Variables de entorno requeridas.**
   - **Salida esperada y códigos de salida.**

---
> Creado: 2026-10-28 · Última revisión: 2026-10-28
