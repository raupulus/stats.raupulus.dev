#!/usr/bin/env bash
set -euo pipefail

# ==============================================================================
# Script de configuración pre-despliegue para GoCD (social-stats-api-websockets)
# ==============================================================================

WORKSCRIPT="$(pwd)"

if [[ $(whoami) == "root" ]]; then
    echo "No puedes ejecutar este script como root" >&2
    exit 1
fi

ENV_EXAMPLE_FILE="${WORKSCRIPT}/.env.example"
if [[ -f "${WORKSCRIPT}/.env.example.production" ]]; then
    ENV_EXAMPLE_FILE="${WORKSCRIPT}/.env.example.production"
fi

if [[ ! -f "${ENV_EXAMPLE_FILE}" ]] || [[ ! -f "${WORKSCRIPT}/deploy/functions.sh" ]]; then
    echo "Este script solo puede ser ejecutado desde la raíz del proyecto." >&2
    exit 1
fi

source "${WORKSCRIPT}/deploy/functions.sh"

echo "=== Generando archivo .env de producción ==="
sync_env_from_example "${ENV_EXAMPLE_FILE}" "${WORKSCRIPT}/.env"

# Sincronizar config/profiles.json desde config/profiles.production.json (versionado en Git)
if [[ -f "${WORKSCRIPT}/config/profiles.production.json" ]]; then
    cp -f "${WORKSCRIPT}/config/profiles.production.json" "${WORKSCRIPT}/config/profiles.json"
    echo "  [CONFIG] Sincronizado config/profiles.json desde config/profiles.production.json"
elif [[ ! -f "${WORKSCRIPT}/config/profiles.json" ]] && [[ -f "${WORKSCRIPT}/config/profiles.example.json" ]]; then
    cp "${WORKSCRIPT}/config/profiles.example.json" "${WORKSCRIPT}/config/profiles.json"
    echo "  [CONFIG] Inicializado config/profiles.json desde config/profiles.example.json"
fi

# Asegurar directorio de datos persistente
mkdir -p "${WORKSCRIPT}/data"
chmod ug+rw "${WORKSCRIPT}/.env" 2>/dev/null || true

echo "=== Configuración completada ==="
