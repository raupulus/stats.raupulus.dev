# Ideas y Métricas Futuras: Estado del Servidor y Hardware (psutil)

Documento de notas para futuras integraciones de telemetría de hardware en el servidor, a mostrar opcionalmente en pantallas de monitorización de escritorio.

---

## 1. Estado del Servidor (Server Health & Hardware Metrics)

### 1.1. Métricas de Interés para Pantalla de Escritorio
- **Uso de CPU:** Porcentaje de uso global (`cpu_percent`) y carga del sistema (load average a 1m, 5m, 15m).
- **Memoria RAM:** Memoria utilizada, memoria disponible y porcentaje de uso (`memory_percent`).
- **Almacenamiento / Disco:** Espacio ocupado y libre en el disco principal o volumen de datos (`disk_usage_percent`, `disk_free_gb`).
- **Uptime:** Tiempo transcurrido desde el último arranque del servidor / contenedor.
- **Temperatura (opcional):** Sensores térmicos de CPU si el hardware del servidor lo expone y se pasa al contenedor.

### 1.2. Propuesta de Implementación Técnica en Python
- Mediante la librería estándar y `psutil` en Python:
  - `psutil.cpu_percent(interval=None)`
  - `psutil.virtual_memory()`
  - `psutil.disk_usage('/')`
  - `psutil.boot_time()`
- Puede integrarse limpiamente como un colector desacoplado (`SystemMetricsCollector`) dentro del mismo bucle de `BaseCollector`, emitiendo sus actualizaciones hacia la API REST y WebSockets en un canal o perfil específico de sistema (ej. `profile="system"` o `/api/v1/system/metrics`).

---
> Creado: 2026-10-28 · Última revisión: 2026-10-29
