#!/bin/bash

# Configuración
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_SCRIPT="$SCRIPT_DIR/yt_channel_transcripts2_checker.py"
VENV_DIR="$SCRIPT_DIR/venv"

# Colores
GREEN='\033[0;32m'
CYAN='\033[0;36m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${CYAN}==============================================${NC}"
echo -e "${CYAN}   YouTube Transcripts - FEDORA WIZARD${NC}"
echo -e "${CYAN}==============================================${NC}"

# Setup Python
if ! command -v python3 &> /dev/null; then echo "Error: Python3 missing"; exit 1; fi
if [ ! -d "$VENV_DIR" ]; then python3 -m venv "$VENV_DIR"; fi
source "$VENV_DIR/bin/activate"
pip install --upgrade pip --quiet
# Aseguramos instalar la versión más reciente que soporta proxies
pip install --upgrade yt-dlp youtube-transcript-api --quiet

echo -e "${GREEN}Entorno listo.${NC}\n"

# Inputs
while [[ -z "$URL" ]]; do read -p "URL (canal/playlist/video): " URL; done

read -p "Carpeta salida (default: channel_transcripts): " OUTDIR
OUTDIR=${OUTDIR:-channel_transcripts}

read -p "Formato (txt/json/srt/vtt) (default: txt): " FORMAT
FORMAT=${FORMAT:-txt}

read -p "Idiomas (ej: es en) (default: es en): " LANGS
LANGS=${LANGS:-es en}

read -p "¿Incluir Shorts? (y/N): " INC_SHORTS
FLAG_SHORTS=""
[[ "$INC_SHORTS" =~ ^[Yy]$ ]] && FLAG_SHORTS="--include-shorts"

# Existing Policy
echo "Política de existentes: 1=same-format, 2=any-format, 3=none"
read -p "Elige (1-3) [1]: " POL_OPT
case $POL_OPT in
    2) EXISTPOL="any-format" ;;
    3) EXISTPOL="none" ;;
    *) EXISTPOL="same-format" ;;
esac

# PROXY SETUP
echo -e "\n${YELLOW}--- Configuración Anti-Ban / Proxy ---${NC}"
echo "1. Sin proxy (Directo - Cuidado con bloqueos)"
echo "2. Webshare (Recomendado si tienes cuenta)"
echo "3. Proxy Genérico (http://user:pass@ip:port)"
read -p "Elige opción (1-3) [1]: " PROXY_OPT

PROXY_ARGS=""
if [[ "$PROXY_OPT" == "2" ]]; then
    read -p "Webshare Username: " WS_USER
    read -p "Webshare Password: " WS_PASS
    if [[ -n "$WS_USER" && -n "$WS_PASS" ]]; then
        PROXY_ARGS="--webshare-user $WS_USER --webshare-pass $WS_PASS"
    else
        echo "Datos incompletos, usando conexión directa."
    fi
elif [[ "$PROXY_OPT" == "3" ]]; then
    read -p "URL del Proxy (http://user:pass@host:port): " P_URL
    if [[ -n "$P_URL" ]]; then
        PROXY_ARGS="--proxy $P_URL"
    fi
fi

# Fechas y Workers
echo -e "\n${YELLOW}--- Opciones Avanzadas ---${NC}"
read -p "Desde (YYYY-MM-DD): " SINCE
read -p "Hasta (YYYY-MM-DD): " UNTIL
read -p "Traducir a (ej. es): " TRANSLATE
read -p "Max videos: " MAXN
read -p "Workers (hilos) [8]: " WORKERS
WORKERS=${WORKERS:-8}

read -p "¿Sobrescribir archivos? (y/N): " OVERW
[[ "$OVERW" =~ ^[Yy]$ ]] && FLAG_OVER="--overwrite" || FLAG_OVER=""

# Build Args
EXTRA_ARGS=""
[[ -n "$SINCE" ]] && EXTRA_ARGS="$EXTRA_ARGS --since $SINCE"
[[ -n "$UNTIL" ]] && EXTRA_ARGS="$EXTRA_ARGS --until $UNTIL"
[[ -n "$TRANSLATE" ]] && EXTRA_ARGS="$EXTRA_ARGS --translate-to $TRANSLATE"
[[ -n "$MAXN" ]] && EXTRA_ARGS="$EXTRA_ARGS --max $MAXN"

echo -e "\n${CYAN}Iniciando descarga...${NC}"
python3 "$PYTHON_SCRIPT" "$URL" \
    -o "$OUTDIR" -f "$FORMAT" --existing-policy "$EXISTPOL" \
    -l $LANGS --workers "$WORKERS" \
    $FLAG_SHORTS $FLAG_OVER $PROXY_ARGS $EXTRA_ARGS

echo -e "\n${GREEN}Finalizado. Enter para salir.${NC}"
read