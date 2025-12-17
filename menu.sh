#!/bin/bash

# 1. Detectar dónde está guardado este archivo
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# 2. Configurar rutas relativas a este archivo
VENV_PYTHON="$SCRIPT_DIR/venv/bin/python3"
SCRIPT_PY="$SCRIPT_DIR/yt_channel_transcripts2_checker.py"

# --- CORRECCIÓN CLAVE ---
# Nos movemos físicamente a la carpeta del script antes de ejecutar.
# Así Python encontrará siempre config.json y channel_transcripts.
cd "$SCRIPT_DIR" || exit 1
# ------------------------

# Colores
CYAN='\033[0;36m'
NC='\033[0m'

echo -e "${CYAN}Iniciando Gestor de Canales (VENV)...${NC}"
echo "Directorio de trabajo: $(pwd)" 

# Ejecutar usando el Python del entorno virtual
"$VENV_PYTHON" "$SCRIPT_PY"

echo ""
echo "Presiona Enter para cerrar."
read