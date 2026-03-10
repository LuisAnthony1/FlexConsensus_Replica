#!/bin/bash
# ==============================================================================
# FlexConsensus - Download Datasets
# ==============================================================================
# Descarga los 3 datasets necesarios para replicar el paper.
#
# Dataset 1: CryoBench (IgG-RL + MDSpike) - ~5 GB
# Dataset 2: EMPIAR-10028 (Ribosome 80S) - ~60 GB
# Dataset 3: EMPIAR-10492 (SARS-CoV-2 Spike) - ~500 GB
#
# Uso:
#   bash scripts/01_download_data.sh [--all|--cryobench|--empiar10028|--empiar10492]
#   bash scripts/01_download_data.sh --cryobench   # solo CryoBench (rapido)
#   bash scripts/01_download_data.sh --all          # todo (requiere ~600GB)
# ==============================================================================

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
DATA_DIR="$PROJECT_DIR/data"
LOG_FILE="$PROJECT_DIR/download_data.log"

log() { echo "[$(date '+%H:%M:%S')] $1" | tee -a "$LOG_FILE"; }

# Parse args
DOWNLOAD_CRYOBENCH=false
DOWNLOAD_EMPIAR10028=false
DOWNLOAD_EMPIAR10492=false

if [ $# -eq 0 ] || [ "$1" == "--all" ]; then
    DOWNLOAD_CRYOBENCH=true
    DOWNLOAD_EMPIAR10028=true
    DOWNLOAD_EMPIAR10492=true
elif [ "$1" == "--cryobench" ]; then
    DOWNLOAD_CRYOBENCH=true
elif [ "$1" == "--empiar10028" ]; then
    DOWNLOAD_EMPIAR10028=true
elif [ "$1" == "--empiar10492" ]; then
    DOWNLOAD_EMPIAR10492=true
else
    echo "Uso: $0 [--all|--cryobench|--empiar10028|--empiar10492]"
    exit 1
fi

log "=== DESCARGA DE DATASETS ==="

# -----------------------------------------------
# Dataset 1: CryoBench (IgG-RL + MDSpike)
# -----------------------------------------------
if $DOWNLOAD_CRYOBENCH; then
    log "[1/3] Descargando CryoBench (IgG-RL + MDSpike)..."
    CRYOBENCH_DIR="$DATA_DIR/cryobench"
    mkdir -p "$CRYOBENCH_DIR"

    if [ ! -d "$CRYOBENCH_DIR/IgG-RL" ]; then
        cd "$CRYOBENCH_DIR"

        # Descargar desde Zenodo (CryoBench official)
        # IgG-RL: dataset sintetico con ground truth
        log "  Descargando IgG-RL..."
        wget -q --show-progress \
            "https://zenodo.org/records/11629428/files/IgG-1D.zip" \
            -O IgG-RL.zip
        unzip -q IgG-RL.zip -d IgG-RL
        rm IgG-RL.zip
        log "  IgG-RL descargado: $(du -sh IgG-RL | cut -f1)"

        # MDSpike: Molecular Dynamics Spike
        log "  Descargando MDSpike..."
        wget -q --show-progress \
            "https://zenodo.org/records/11629428/files/Spike-MD.zip" \
            -O MDSpike.zip
        unzip -q MDSpike.zip -d MDSpike
        rm MDSpike.zip
        log "  MDSpike descargado: $(du -sh MDSpike | cut -f1)"

        cd "$PROJECT_DIR"
    else
        log "  CryoBench ya existe, saltando."
    fi

    # Verificar estructura
    log "  Verificando CryoBench..."
    for subdir in IgG-RL MDSpike; do
        if [ -d "$CRYOBENCH_DIR/$subdir" ]; then
            log "    OK: $subdir ($(find "$CRYOBENCH_DIR/$subdir" -name "*.mrcs" -o -name "*.mrc" -o -name "*.star" | wc -l) archivos cryo-EM)"
        else
            log "    FALTA: $subdir"
        fi
    done
fi

# -----------------------------------------------
# Dataset 2: EMPIAR-10028 (Ribosome 80S)
# -----------------------------------------------
if $DOWNLOAD_EMPIAR10028; then
    log "[2/3] Descargando EMPIAR-10028 (Ribosome 80S)..."
    EMPIAR_DIR="$DATA_DIR/empiar_10028"
    mkdir -p "$EMPIAR_DIR"

    if [ ! -f "$EMPIAR_DIR/.download_complete" ]; then
        cd "$EMPIAR_DIR"

        # Opcion 1: Aspera (rapido, ~60GB)
        if command -v ascp &> /dev/null; then
            log "  Usando Aspera para descarga rapida..."
            ascp -QT -l 500M -P 33001 \
                -i "$HOME/.aspera/connect/etc/asperaweb_id_dsa.openssh" \
                era-fasp@fasp.ebi.ac.uk:/empiar/world_availability/10028/ \
                . 2>&1 | tee -a "$LOG_FILE"
        else
            # Opcion 2: wget via FTP (lento pero funciona siempre)
            log "  Aspera no disponible, usando wget (sera mas lento)..."
            wget -r -nH --cut-dirs=5 --no-parent -q --show-progress \
                "ftp://ftp.ebi.ac.uk/empiar/world_availability/10028/data/" \
                -P . 2>&1 | tee -a "$LOG_FILE"
        fi

        touch .download_complete
        log "  EMPIAR-10028 descargado: $(du -sh . | cut -f1)"
        cd "$PROJECT_DIR"
    else
        log "  EMPIAR-10028 ya descargado."
    fi
fi

# -----------------------------------------------
# Dataset 3: EMPIAR-10492 (SARS-CoV-2 Spike)
# -----------------------------------------------
if $DOWNLOAD_EMPIAR10492; then
    log "[3/3] Descargando EMPIAR-10492 (SARS-CoV-2 Spike)..."
    log "  ADVERTENCIA: Este dataset es ~500GB. Asegurate de tener espacio."

    EMPIAR_DIR="$DATA_DIR/empiar_10492"
    mkdir -p "$EMPIAR_DIR"

    # Verificar espacio disponible
    AVAILABLE_GB=$(df -BG "$EMPIAR_DIR" | tail -1 | awk '{print $4}' | tr -d 'G')
    if [ "$AVAILABLE_GB" -lt 550 ]; then
        log "  ERROR: Solo ${AVAILABLE_GB}GB disponibles. Se necesitan ~550GB."
        log "  Considera montar un volumen EBS adicional:"
        log "    sudo mkfs.ext4 /dev/xvdf"
        log "    sudo mount /dev/xvdf $EMPIAR_DIR"
        exit 1
    fi

    if [ ! -f "$EMPIAR_DIR/.download_complete" ]; then
        cd "$EMPIAR_DIR"

        if command -v ascp &> /dev/null; then
            log "  Usando Aspera..."
            ascp -QT -l 500M -P 33001 \
                -i "$HOME/.aspera/connect/etc/asperaweb_id_dsa.openssh" \
                era-fasp@fasp.ebi.ac.uk:/empiar/world_availability/10492/ \
                . 2>&1 | tee -a "$LOG_FILE"
        else
            log "  Usando wget (sera MUY lento para 500GB)..."
            wget -r -nH --cut-dirs=5 --no-parent -q --show-progress \
                "ftp://ftp.ebi.ac.uk/empiar/world_availability/10492/data/" \
                -P . 2>&1 | tee -a "$LOG_FILE"
        fi

        touch .download_complete
        log "  EMPIAR-10492 descargado: $(du -sh . | cut -f1)"
        cd "$PROJECT_DIR"
    else
        log "  EMPIAR-10492 ya descargado."
    fi
fi

# -----------------------------------------------
# Resumen
# -----------------------------------------------
log ""
log "=== DESCARGA COMPLETADA ==="
log "Estructura de datos:"
find "$DATA_DIR" -maxdepth 2 -type d | sort | while read d; do
    log "  $d"
done
log ""
log "Siguiente paso: python scripts/02_preprocess.py --dataset cryobench"
