# Integración API Externa: Binance Public Market API (`CryptoCollector`)

Integración con la API pública de mercado de Binance (`https://api.binance.com/api/v3`) para obtener precios spot y estadísticas de 24h de criptomonedas (Bitcoin `BTC`, Cardano `ADA`, etc.) en dólares (`USDT`) y euros (`EUR`) sin necesidad de API Key ni tokens.

---

## 1. Endpoints Utilizados
1. **Batch 24hr Ticker (múltiples pares en una sola petición):**
   - `GET https://api.binance.com/api/v3/ticker/24hr?symbols=["BTCUSDT","BTCEUR","ADAUSDT","ADAEUR"]`
2. **Fallback Individual 24hr Ticker (si algún par del batch devuelve HTTP `400 -1121 Invalid symbol`):**
   - `GET https://api.binance.com/api/v3/ticker/24hr?symbol=BTCUSDT`

---

## 2. Mapeo de Campos
Para cada activo configurado (ej. `account_key = "btc"`, `base_symbol = "BTC"`):
- Par `{SYMBOL}USDT`:
  - `lastPrice` $\rightarrow$ `price_usd` (`float`).
  - `priceChange` $\rightarrow$ `price_change_24h_usd` (`float`).
  - `priceChangePercent` $\rightarrow$ `price_change_24h_pct` (`float`).
  - `highPrice` $\rightarrow$ `high_24h_usd` (`float`).
  - `lowPrice` $\rightarrow$ `low_24h_usd` (`float`).
- Par `{SYMBOL}EUR`:
  - `lastPrice` $\rightarrow$ `price_eur` (`float`).
  - `priceChange` $\rightarrow$ `price_change_24h_eur` (`float`).
  - `priceChangePercent` $\rightarrow$ `price_change_24h_eur_pct` (`float`).
  - `highPrice` $\rightarrow$ `high_24h_eur` (`float`).
  - `lowPrice` $\rightarrow$ `low_24h_eur` (`float`).

---

## 3. Autenticación y Cuotas
- No requiere ninguna clave ni token de autenticación.
- Cuota pública por IP: 1.200 unidades de peso por minuto. Una llamada batch a `/api/v3/ticker/24hr` con 1–20 símbolos consume 1–20 unidades de peso; con `POLL_INTERVAL_CRYPTO=60` consume $<0.2\%$ del límite por minuto.
- **Trampa conocida verificada:** Si cualquier símbolo de la lista `symbols=[...]` no existe en Binance, el endpoint devuelve `HTTP 400 {"code": -1121, "msg": "Invalid symbol."}` para todo el lote. `CryptoCollector` detecta el `HTTP 400` y realiza automáticamente consultas individuales por par para que un símbolo inexistente nunca invalide los precios de `BTC` o `ADA`.

---

## 4. Estado de Verificación Empírica
- Verificado empíricamente con peticiones reales en vivo contra `https://api.binance.com/api/v3/ticker/24hr` el `2026-10-28` (tanto lote válido `["BTCUSDT","BTCEUR","ADAUSDT","ADAEUR"]` como comportamiento ante par inválido `HTTP 400 -1121`) y cubierto por tests unitarios en [`tests/unit/collectors/test_crypto.py`](../../../tests/unit/collectors/test_crypto.py).

---
> Creado: 2026-10-28 · Última revisión: 2026-10-28
