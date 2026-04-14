#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_DIR="$ROOT_DIR/.venv"

pick_python() {
    if [[ -n "${PYTHON_BIN:-}" ]]; then
        printf '%s\n' "$PYTHON_BIN"
        return
    fi

    local candidate
    for candidate in python3.12 python3.11 python3.10; do
        if command -v "$candidate" >/dev/null 2>&1; then
            command -v "$candidate"
            return
        fi
    done

    echo "No Python 3.10+ interpreter found on PATH." >&2
    exit 1
}

PYTHON_BIN="$(pick_python)"
PYTHON_DIST_ROOT="$("$PYTHON_BIN" -c 'import pathlib, sys; print(pathlib.Path(sys.executable).resolve().parent.parent)')"

if [[ -d "$VENV_DIR" ]]; then
    BACKUP_DIR="${ROOT_DIR}/.venv-broken-$(date +%Y%m%d-%H%M%S)"
    mv "$VENV_DIR" "$BACKUP_DIR"
    echo "Backed up existing .venv to ${BACKUP_DIR}"
fi

"$PYTHON_BIN" -m venv --without-pip "$VENV_DIR"
printf '%s\n' "$PYTHON_DIST_ROOT" > "$VENV_DIR/.pythonhome"

PYTHONHOME="$PYTHON_DIST_ROOT" "$VENV_DIR/bin/python" -m ensurepip --upgrade
PYTHONHOME="$PYTHON_DIST_ROOT" "$VENV_DIR/bin/python" -m pip install --upgrade pip setuptools wheel
(
    cd "$ROOT_DIR"
    PYTHONHOME="$PYTHON_DIST_ROOT" "$VENV_DIR/bin/python" -m pip install -e '.[dev]'
)

if ! grep -q "JPTranscript UV Python fix" "$VENV_DIR/bin/activate"; then
    cat >> "$VENV_DIR/bin/activate" <<'EOF'

# JPTranscript UV Python fix
if [ -f "$VIRTUAL_ENV/.pythonhome" ] ; then
    PYTHONHOME="$(cat "$VIRTUAL_ENV/.pythonhome")"
    export PYTHONHOME
fi
EOF
fi

cat > "$VENV_DIR/bin/adk" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
PYTHONHOME_FILE="$VENV_DIR/.pythonhome"

if [[ -f "$PYTHONHOME_FILE" ]]; then
    export PYTHONHOME="$(cat "$PYTHONHOME_FILE")"
fi

exec "$VENV_DIR/bin/python" -m google.adk.cli "$@"
EOF
chmod +x "$VENV_DIR/bin/adk"

echo
echo "Virtual environment rebuilt successfully."
echo "Python: $PYTHON_BIN"
echo "PYTHONHOME: $PYTHON_DIST_ROOT"
echo
echo "Next step:"
echo "  source .venv/bin/activate"
