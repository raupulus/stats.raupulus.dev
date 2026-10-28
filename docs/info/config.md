# Módulo: `config` (`src/social_stats/config/`)

Sistema de configuración tipado del servidor: carga y validación de variables de entorno (`.env`) y perfiles declarativos multicanal en formato JSON (`config/profiles.json`) o YAML (`config/profiles.yaml`).

---

## 1. Qué hace y qué NO hace

### 1.1. Qué hace
- Carga y valida las variables de entorno del servidor mediante `Settings(BaseSettings)` (`pydantic-settings`).
- Resuelve dinámicamente intervalos de recolección por plataforma (`get_poll_interval`) y credenciales multicuentas de Instagram (`get_instagram_credentials(credentials_ref)`) y Keycounter (`get_keycounter_token(credentials_ref)`).
- Parsea y valida el archivo declarativo `config/profiles.json` (o `config/profiles.yaml`) mediante `ProfilesRegistry`, `ProfileConfig` y `AccountConfig`.
- Soporta el atributo booleano `enable` (o `enabled`) tanto a nivel de perfil como de cuenta individual para activar/desactivar perfiles completos o canales concretos.
- Soporta el atributo booleano `public` (por defecto `true`) tanto a nivel de perfil como de cuenta individual para controlar qué perfiles y cuentas se exponen en el WebSocket público (`/ws/public`). Si un perfil tiene `"public": false`, ninguna de sus cuentas se expone públicamente.
- Soporta el atributo `interval_minutes` (o alias `poll_interval_minutes` / `interval`) en minutos por cuenta individual (y como valor por defecto opcional en el perfil) para gestionar la frecuencia de consulta de cada cuenta de forma independiente.
- Normaliza y calcula de forma determinista el identificador único de cuenta (`account_key`) para cada red social, activo cripto y keycounter (`youtube`, `twitter`, `instagram`, `bluesky`, `mastodon`, `tiktok`, `linkedin`, `crypto`, `keycounter`), incluyendo alias como `bitcoin` $\rightarrow$ `btc`, `cardano` $\rightarrow$ `ada` y `keystrokes` $\rightarrow$ `keycounter`.
- Deduplica cuentas repetidas entre perfiles mediante `get_unique_accounts_by_platform()` fusionando su estado activo/público y seleccionando el menor `interval_minutes` configurado.

### 1.2. Qué NO hace
- No realiza llamadas de red ni resuelve `@handle` de YouTube a `UC...` contra la API de Google (esa responsabilidad pertenece a `YouTubeCollector`).
- No persiste tokens rotados ni estado en SQLite (esa responsabilidad pertenece al módulo `storage`).

---

## 2. Modelo de datos
- `Settings` (`src/social_stats/config/settings.py`):
  - `app_env`, `app_host`, `app_port`, `log_level`, `profiles_config_path`, `sqlite_db_path`, `public_dir_path`, `cors_allowed_origins`.
  - Seguridad y canales: `api_bearer_token`, `ws_public_allowed_origins`, `ws_public_max_per_ip`, `ws_public_max_connections`.
  - Intervalos `poll_interval_<platform>` (mínimo 10 segundos) y `snapshot_retention_days`.
  - Credenciales opcionales por plataforma (`youtube_api_key`, `ig_main_user_id`, `ig_main_access_token`, `twitter_auth_token_cookie`, `twitter_ct0_cookie`, `tiktok_client_key`, `tiktok_client_secret`, `linkedin_access_token`, `linkedin_li_at_cookie`).
- `AccountConfig` (`src/social_stats/config/profiles.py`):
  - `id`, `handle`, `instance`, `label`, `credentials_ref`, `account_type` (`"personal"` | `"organization"`), `enabled` (alias `enable`), `public`, `interval_minutes` (tiempo de consulta individual en minutos), `platform`, `account_key`.
- `ProfileConfig`:
  - `profile_id` (slug `^[a-z0-9_-]+$`), `name`, `description`, `enabled` (alias `enable`), `public`, `interval_minutes` (intervalo por defecto opcional para las cuentas del perfil), `accounts: dict[str, list[AccountConfig]]`.
- `ProfilesRegistry`:
  - `version`, `profiles: dict[str, ProfileConfig]`.

---

## 3. Flujos principales
1. Al iniciar la aplicación, `get_settings()` lee el entorno y `.env`.
2. `load_profiles_config(path)` abre el archivo JSON o YAML, verifica que la raíz sea un diccionario y ejecuta `ProfilesRegistry.model_validate()`.
3. Durante la validación:
   - Se comprueba que cada clave `profile_id` cumpla `^[a-z0-9_-]+$`.
   - Para cada cuenta se calcula su `account_key` inmutable (`UC...` o handle normalizado en YouTube, `handle@instance` en Mastodon, `handle` sin `@` en minúsculas en el resto).
   - Se propaga `enabled = acc.enabled and profile.enabled` y `public = acc.public and profile.public`.
   - Se rechazan cuentas duplicadas dentro de una misma plataforma y perfil.
4. El planificador consulta `registry.get_unique_accounts_by_platform(only_enabled=True)` para obtener la lista única de cuentas activas por plataforma.

---

## 4. Puntos de entrada (Auth, permisos y límites)
- `get_settings() -> Settings`: Singleton cacheado con `@lru_cache`.
- `load_profiles_config(path: Path | str) -> ProfilesRegistry`: Lanza `FileNotFoundError`, `ValueError` o `ValidationError` ante errores de configuración.
- `ProfilesRegistry.get_unique_accounts_by_platform(only_enabled: bool = True, only_public: bool = False) -> dict[str, list[AccountConfig]]`.

---

## 5. Dependencias en ambos sentidos
- **Depende de:** `pydantic`, `pydantic-settings`, `PyYAML` (`yaml`).
- **Consumido por:** `main`, `collectors`, `services` (`aggregator`, `scheduler`, `ws_manager`), `api`.

---

## 6. Configuración
| Variable / Parámetro | Tipo | Valor por defecto | Efecto / Comportamiento |
|---|---|---|---|
| `APP_ENV` | `str` | `"production"` | Entorno de ejecución (`production` oculta `/docs`, `/redoc` y `/openapi.json`) |
| `APP_HOST` | `str` | `"0.0.0.0"` | Interfaz de escucha del servidor FastAPI |
| `APP_PORT` | `int` | `8000` | Puerto TCP de escucha |
| `LOG_LEVEL` | `str` | `"INFO"` | Nivel de logging |
| `PROFILES_CONFIG_PATH` | `Path` | `config/profiles.json` | Ruta al archivo JSON o YAML de perfiles |
| `SQLITE_DB_PATH` | `Path` | `data/stats.db` | Ruta al archivo SQLite de snapshots |
| `PUBLIC_DIR_PATH` | `Path` | `public` | Ruta al directorio estático de la web pública |
| `API_BEARER_TOKEN` | `str` | `""` | Token Bearer obligatorio para API REST privada (`/api/v1/*`) y WebSockets privados (`/ws/stats`, `/ws/profiles/{id}`) |
| `CORS_ALLOWED_ORIGINS` | `str` | `"https://stats.raupulus.dev,https://raupulus.dev,http://localhost:8000,http://127.0.0.1:8000"` | Orígenes CORS permitidos separados por coma |
| `WS_PUBLIC_ALLOWED_ORIGINS` | `str` | `"https://stats.raupulus.dev,https://raupulus.dev,http://localhost:8000,http://127.0.0.1:8000"` | Cabeceras `Origin` permitidas en `/ws/public` |
| `WS_PUBLIC_MAX_PER_IP` | `int` | `5` | Límite de conexiones simultáneas por IP en `/ws/public` |
| `WS_PUBLIC_MAX_CONNECTIONS` | `int` | `200` | Límite global de conexiones simultáneas en `/ws/public` |
| `SNAPSHOT_RETENTION_DAYS` | `int` | `30` | Días de retención de snapshots históricos |
| `KEYCOUNTER_API_URL` | `str` | `"https://api.raupulus.dev/api/v2/keycounter/stats"` | URL del endpoint de estadísticas de Keycounter |
| `KEYCOUNTER_API_TOKEN` | `str` | `""` | Token Bearer de autenticación para Keycounter |

---

## 7. Trampas conocidas y consideraciones de diseño
- En YouTube, si se define `id` (`UC...`), ese valor es el `account_key`. Si solo se define `handle`, el `account_key` es el handle sin `@` en minúsculas y se mantiene inmutable aunque el colector resuelva internamente el `UC...` para consultar Google APIs.
- Tanto `config/profiles.json` como `config/profiles.yaml` están excluidos en `.gitignore` para evitar exponer configuraciones locales del servidor; las plantillas versionadas son `config/profiles.example.json` y `config/profiles.example.yaml`.

---

## 8. Tests que lo cubren
- [`tests/unit/test_profiles_config.py`](../../tests/unit/test_profiles_config.py)
- Comando: `.venv/bin/pytest tests/unit/test_profiles_config.py`

---

## 9. Pendiente real
- Ninguno. Módulo verificado con tests unitarios.

---
> Creado: 2026-10-28 · Última revisión: 2026-10-28
