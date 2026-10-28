# Ideas y Métricas Futuras: Criptomonedas y Estado del Servidor

Documento de notas para futuras integraciones a mostrar en la pantalla de escritorio junto a las estadísticas de redes sociales.

---

## 1. Precios de Criptomonedas (BTC y ADA) — [IMPLEMENTADO]

> **Nota de promoción:** Esta integración ya ha sido implementada en código ([`src/social_stats/collectors/crypto.py`](../../src/social_stats/collectors/crypto.py)) y documentada en la documentación viva ([`docs/info/apis/binance.md`](../info/apis/binance.md) y [`docs/info/collectors.md`](../info/collectors.md)).

### 1.1. Requisitos
- Obtener precio en tiempo real de:
  - **Bitcoin (BTC)** en Dólares (USD/USDT) y Euros (EUR).
  - **Cardano (ADA)** en Dólares (USD/USDT) y Euros (EUR).
- Operación 100% desatendida y gratuita, sin necesidad de tokens ni autenticación obligatoria.

### 1.2. Viabilidad y Proveedor Sugerido (Binance Public API)
- **Endpoint oficial sin tokens:** Binance expone endpoints públicos de mercado que no requieren API Key ni registro:
  - Consulta puntual única de múltiples pares:
    ```http
    GET https://api.binance.com/api/v3/ticker/price?symbols=["BTCUSDT","BTCEUR","ADAUSDT","ADAEUR"]
    ```
  - Respuesta JSON directa:
    ```json
    [
      {"symbol": "BTCUSDT", "price": "67420.50"},
      {"symbol": "BTCEUR",  "price": "62150.10"},
      {"symbol": "ADAUSDT", "price": "0.4850"},
      {"symbol": "ADAEUR",  "price": "0.4470"}
    ]
    ```
  - Estadísticas adicionales (cambio 24h, máximos, mínimos):
    ```http
    GET https://api.binance.com/api/v3/ticker/24hr?symbols=["BTCUSDT","BTCEUR","ADAUSDT","ADAEUR"]
    ```
- **Límites de cuota (Rate limits):** 1.200 créditos de peso por minuto por IP. Una consulta batch de tickers cuesta solo entre 1 y 2 créditos de peso. Haciendo un sondeo cada 30–60 segundos se consume menos del 0,2% del límite.
- **Alternativas de respaldo (sin API key):** CoinGecko (`/api/v3/simple/price`) o Kraken Public API (`/0/public/Ticker`).

---

## 2. Estado del Servidor (Server Health & Hardware Metrics)

### 2.1. Métricas de Interés para Pantalla de Escritorio
- **Uso de CPU:** Porcentaje de uso global (`cpu_percent`) y carga del sistema (load average a 1m, 5m, 15m).
- **Memoria RAM:** Memoria utilizada, memoria disponible y porcentaje de uso (`memory_percent`).
- **Almacenamiento / Disco:** Espacio ocupado y libre en el disco principal o volumen de datos (`disk_usage_percent`, `disk_free_gb`).
- **Uptime:** Tiempo transcurrido desde el último arranque del servidor / contenedor.
- **Temperatura (opcional):** Sensores térmicos de CPU si el hardware del servidor lo expone y se pasa al contenedor.

### 2.2. Implementación Técnica en Python
- Mediante la librería estándar y `psutil` en Python:
  - `psutil.cpu_percent(interval=None)`
  - `psutil.virtual_memory()`
  - `psutil.disk_usage('/')`
  - `psutil.boot_time()`
- Puede integrarse limpiamente como un colector desacoplado (`SystemMetricsCollector`) dentro del mismo bucle de `BaseCollector`, emitiendo sus actualizaciones hacia la API REST y WebSockets en un canal o perfil específico de sistema (ej. `profile="system"` o `/api/v1/system/metrics`).

---
> Creado: 2026-10-28 · Última revisión: 2026-10-28

