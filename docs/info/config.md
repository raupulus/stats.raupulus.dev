# Módulo: `config` (`src/social_stats/config/`)

Sistema de configuración tipado del servidor: carga y validación de variables de entorno (`.env`) y perfiles declarativos multicanal (`config/profiles.yaml`).

---

## 1. Qué hace y qué NO hace

### 1.1. Qué hace
- Carga y valida las variables de entorno del servidor mediante `Settings(BaseSettings)` (`pydantic-settings`).
- Resuelve dinámicamente intervalos de recolección por plataforma (`get_poll_interval`) y credenciales multicuentas de Instagram (`get_instagram_credentials(credentials_ref)`).
- Parsea y valida el archivo declarativo `config/profiles.yaml` mediante `ProfilesRegistry`, `ProfileConfig` y `AccountConfig`.
- Normaliza y calcula de forma determinista el identificador único de cuenta (`account_key`) para cada red social y plataforma de mercado (`youtube`, `twitter`, `instagram`, `bluesky`, `mastodon`, `tiktok`, `linkedin`, `crypto`), incluyendo alias como `bitcoin` $\rightarrow$ `btc` y `cardano` $\rightarrow$ `ada`.
- Deduplica cuentas repetidas entre perfiles mediante `get_unique_accounts_by_platform()` para evitar peticiones HTTP redundantes en los colectores.

### 1.2. Qué NO hace
- No realiza llamadas de red ni resuelve `@handle` de YouTube a `UC...` contra la API de Google (esa responsabilidad pertenece a `YouTubeCollector`).
- No persiste tokens rotados ni estado en SQLite (esa responsabilidad pertenece al módulo `storage`).

---

## 2. Modelo de datos
- `Settings` (`src/social_stats/config/settings.py`):
  - `app_env`, `app_host`, `app_port`, `log_level`, `profiles_config_path`, `sqlite_db_path`, `cors_allowed_origins`.
  - Intervalos `poll_interval_<platform>` (mínimo 10 segundos) y `snapshot_retention_days`.
  - Credenciales opcionales por plataforma (`youtube_api_key`, `ig_main_user_id`, `ig_main_access_token`, `twitter_auth_token_cookie`, `twitter_ct0_cookie`, `tiktok_client_key`, `tiktok_client_secret`, `linkedin_access_token`, `linkedin_li_at_cookie`).
- `AccountConfig` (`src/social_stats/config/profiles.py`):
  - `id`, `handle`, `instance`, `label`, `credentials_ref`, `account_type` (`"personal"` | `"organization"`), `enabled`, `platform`, `account_key`.
- `ProfileConfig`:
  - `profile_id` (slug `^[a-z0-9_-]+$`), `name`, `description`, `accounts: dict[str, list[AccountConfig]]`.
- `ProfilesRegistry`:
  - `version`, `profiles: dict[str, ProfileConfig]`.

---

## 3. Flujos principales
1. Al iniciar la aplicación, `get_settings()` lee el entorno y `.env`.
2. `load_profiles_config(path)` abre el archivo YAML, verifica que la raíz sea un diccionario y ejecuta `ProfilesRegistry.model_validate()`.
3. Durante la validación:
   - Se comprueba que cada clave `profile_id` cumpla `^[a-z0-9_-]+$`.
   - Para cada cuenta se calcula su `account_key` inmutable (`UC...` o handle normalizado en YouTube, `handle@instance` en Mastodon, `handle` sin `@` en minúsculas en el resto).
   - Se rechazan cuentas duplicadas dentro de una misma plataforma y perfil.
4. El planificador consulta `registry.get_unique_accounts_by_platform(only_enabled=True)` para obtener la lista única de cuentas activas por plataforma.

---

## 4. Puntos de entrada (Auth, permisos y límites)
- `get_settings() -> Settings`: Singleton cacheado con `@lru_cache`.
- `load_profiles_config(path: Path | str) -> ProfilesRegistry`: Lanza `FileNotFoundError`, `ValueError` o `ValidationError` ante errores de configuración.
- `ProfilesRegistry.get_unique_accounts_by_platform(only_enabled: bool = True) -> dict[str, list[AccountConfig]]`.

---

## 5. Dependencias en ambos sentidos
- **Depende de:** `pydantic`, `pydantic-settings`, `PyYAML` (`yaml`).
- **Consumido por:** `main`, `collectors`, `services` (`aggregator`, `scheduler`), `api`.

---

## 6. Configuración
| Variable / Parámetro | Tipo | Valor por defecto | Efecto / Comportamiento |
|---|---|---|---|
| `APP_ENV` | `str` | `"production"` | Entorno de ejecución |
| `APP_HOST` | `str` | `"0.0.0.0"` | Interfaz de escucha del servidor FastAPI |
| `APP_PORT` | `int` | `8000` | Puerto TCP de escucha |
| `LOG_LEVEL` | `str` | `"INFO"` | Nivel de logging |
| `PROFILES_CONFIG_PATH` | `Path` | `config/profiles.yaml` | Ruta al archivo YAML de perfiles |
| `SQLITE_DB_PATH` | `Path` | `data/stats.db` | Ruta al archivo SQLite de snapshots |
| `CORS_ALLOWED_ORIGINS` | `str` | `"*"` | Orígenes CORS permitidos separados por coma |
| `SNAPSHOT_RETENTION_DAYS` | `int` | `30` | Días de retención de snapshots históricos |

---

## 7. Trampas conocidas y consideraciones de diseño
- En YouTube, si se define `id` (`UC...`), ese valor es el `account_key`. Si solo se define `handle`, el `account_key` es el handle sin `@` en minúsculas y se mantiene inmutable aunque el colector resuelva internamente el `UC...` para consultar Google APIs.
- `config/profiles.yaml` está excluido en `.gitignore` para evitar exponer configuraciones locales; la plantilla versionada es `config/profiles.example.yaml`.

---

## 8. Tests que lo cubren
- [`tests/unit/test_profiles_config.py`](../../tests/unit/test_profiles_config.py)
- Comando: `.venv/bin/pytest tests/unit/test_profiles_config.py`

---

## 9. Pendiente real
- Ninguno. Módulo verificado con tests unitarios.

---
> Creado: 2026-10-28 · Última revisión: 2026-10-28
