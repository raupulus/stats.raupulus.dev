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

if [[ ! -f "${WORKSCRIPT}/.env.example" ]] || [[ ! -f "${WORKSCRIPT}/deploy/functions.sh" ]]; then
    echo "Este script solo puede ser ejecutado desde la raíz del proyecto." >&2
    exit 1
fi

source "${WORKSCRIPT}/deploy/functions.sh"

echo "=== Generando archivo .env de producción ==="
sync_env_from_example "${WORKSCRIPT}/.env.example" "${WORKSCRIPT}/.env"

# Variables adicionales de volúmenes Docker si se definen en GoCD
for extra_key in DATA_DIR CONFIG_DIR; do
    if [[ -n "${!extra_key:-}" ]]; then
        replace_or_add_var_in_file "${WORKSCRIPT}/.env" "${extra_key}" "${!extra_key}"
        echo "  [ENV] Variable adicional inyectada: ${extra_key}"
    fi
done

# Inicializar config/profiles.json si no existe
if [[ ! -f "${WORKSCRIPT}/config/profiles.json" ]]; then
    if [[ -f "${WORKSCRIPT}/config/profiles.production.json" ]]; then
        cp "${WORKSCRIPT}/config/profiles.production.json" "${WORKSCRIPT}/config/profiles.json"
        echo "  [CONFIG] Inicializado config/profiles.json desde config/profiles.production.json"
    elif [[ -f "${WORKSCRIPT}/config/profiles.example.json" ]]; then
        cp "${WORKSCRIPT}/config/profiles.example.json" "${WORKSCRIPT}/config/profiles.json"
        echo "  [CONFIG] Inicializado config/profiles.json desde config/profiles.example.json"
    fi
fi

# Asegurar directorio de datos persistente
mkdir -p "${WORKSCRIPT}/data"
chmod ug+rw "${WORKSCRIPT}/.env" 2>/dev/null || true

echo "=== Configuración completada ==="
