#!/usr/bin/env bash
set -euo pipefail

# ==============================================================================
# Funciones auxiliares para despliegue automatizado con GoCD y Docker
# ==============================================================================

##
## Reemplaza o añade una variable KEY=VALUE en un archivo .env de forma segura
## (soporta caracteres especiales como /, |, &, = sin romper sed).
##
replace_or_add_var_in_file() {
    local file="${1}"
    local var_name="${2}"
    local var_value="${3:-}"

    if [[ ! -f "${file}" ]]; then
        touch "${file}"
    fi

    python3 - "${file}" "${var_name}" "${var_value}" <<'PYEOF'
import re
import sys
from pathlib import Path

env_path = Path(sys.argv[1])
key = sys.argv[2]
val = sys.argv[3]

lines = env_path.read_text(encoding="utf-8").splitlines()
pattern = re.compile(rf"^\s*#?\s*{re.escape(key)}\s*=.*$")
replaced = False
new_lines = []

for line in lines:
    if not replaced and pattern.match(line):
        new_lines.append(f"{key}={val}")
        replaced = True
    else:
        new_lines.append(line)

if not replaced:
    new_lines.append(f"{key}={val}")

env_path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
PYEOF
}

##
## Sincroniza automáticamente todas las variables definidas en .env.example
## que estén presentes y no vacías en el entorno del pipeline GoCD.
##
sync_env_from_example() {
    local example_file="${1}"
    local target_file="${2}"

    if [[ ! -f "${example_file}" ]]; then
        echo "No existe ${example_file}" >&2
        return 1
    fi

    cp -f "${example_file}" "${target_file}"
    chmod 640 "${target_file}" 2>/dev/null || true

    local var_keys
    var_keys=$(grep -E '^[A-Za-z_][A-Za-z0-9_]*=' "${example_file}" | cut -d'=' -f1 || true)

    for key in ${var_keys}; do
        if [[ -n "${!key:-}" ]]; then
            replace_or_add_var_in_file "${target_file}" "${key}" "${!key}"
            echo "  [ENV] Variable inyectada: ${key}"
        fi
    done
}
