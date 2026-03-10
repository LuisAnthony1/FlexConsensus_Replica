#!/bin/bash
# ==============================================================================
# FlexConsensus - Setup AWS GPU Instance
# ==============================================================================
# Ejecutar una sola vez al crear la instancia EC2.
# Instancia recomendada: g5.2xlarge (NVIDIA A10G, 24GB VRAM, 32GB RAM)
# AMI recomendada: Deep Learning AMI GPU PyTorch 2.1 (Ubuntu 22.04)
#
# Uso:
#   chmod +x scripts/00_setup_aws.sh
#   bash scripts/00_setup_aws.sh
# ==============================================================================

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
LOG_FILE="$PROJECT_DIR/setup_aws.log"

log() { echo "[$(date '+%H:%M:%S')] $1" | tee -a "$LOG_FILE"; }

log "=== FLEXCONSENSUS AWS SETUP ==="
log "Project dir: $PROJECT_DIR"

# -----------------------------------------------
# 1. Verificar GPU
# -----------------------------------------------
log "[1/8] Verificando GPU..."
if ! command -v nvidia-smi &> /dev/null; then
    log "ERROR: nvidia-smi no encontrado. Usa una AMI con GPU."
    exit 1
fi
nvidia-smi --query-gpu=name,memory.total --format=csv,noheader | tee -a "$LOG_FILE"
GPU_MEM=$(nvidia-smi --query-gpu=memory.total --format=csv,noheader,nounits | head -1 | tr -d ' ')
if [ "$GPU_MEM" -lt 10000 ]; then
    log "WARNING: GPU con menos de 10GB VRAM. Se recomienda >=24GB."
fi

# -----------------------------------------------
# 2. Dependencias del sistema
# -----------------------------------------------
log "[2/8] Instalando dependencias del sistema..."
sudo apt-get update -qq
sudo apt-get install -y -qq \
    build-essential cmake git wget curl unzip \
    libfftw3-dev libhdf5-dev libtiff-dev \
    libsqlite3-dev libopenmpi-dev openmpi-bin \
    pigz aria2

# -----------------------------------------------
# 3. Miniconda (si no existe)
# -----------------------------------------------
log "[3/8] Configurando Conda..."
if ! command -v conda &> /dev/null; then
    wget -q https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh -O /tmp/miniconda.sh
    bash /tmp/miniconda.sh -b -p "$HOME/miniconda3"
    eval "$($HOME/miniconda3/bin/conda shell.bash hook)"
    conda init bash
    rm /tmp/miniconda.sh
    log "  Conda instalado en $HOME/miniconda3"
else
    eval "$(conda shell.bash hook)"
    log "  Conda ya instalado: $(conda --version)"
fi

# -----------------------------------------------
# 4. Crear entorno conda
# -----------------------------------------------
log "[4/8] Creando entorno flexconsensus..."
if conda env list | grep -q "flexconsensus"; then
    log "  Entorno ya existe, actualizando..."
    conda env update -f "$PROJECT_DIR/environment.yml" --prune
else
    conda env create -f "$PROJECT_DIR/environment.yml"
fi
conda activate flexconsensus

# -----------------------------------------------
# 5. Verificar instalaciones
# -----------------------------------------------
log "[5/8] Verificando instalaciones..."

# Python
python -c "import sys; print(f'  Python: {sys.version}')" | tee -a "$LOG_FILE"

# PyTorch + CUDA
python -c "
import torch
print(f'  PyTorch: {torch.__version__}')
print(f'  CUDA disponible: {torch.cuda.is_available()}')
if torch.cuda.is_available():
    print(f'  GPU: {torch.cuda.get_device_name(0)}')
    print(f'  VRAM: {torch.cuda.get_device_properties(0).total_mem / 1e9:.1f} GB')
" | tee -a "$LOG_FILE"

# TensorFlow + GPU
python -c "
import tensorflow as tf
print(f'  TensorFlow: {tf.__version__}')
gpus = tf.config.list_physical_devices('GPU')
print(f'  TF GPUs: {len(gpus)}')
for g in gpus:
    print(f'    {g}')
" | tee -a "$LOG_FILE"

# CryoDRGN
python -c "import cryodrgn; print(f'  CryoDRGN: OK')" 2>/dev/null | tee -a "$LOG_FILE" || log "  WARNING: CryoDRGN import failed"

# -----------------------------------------------
# 6. Instalar Scipion 3.0
# -----------------------------------------------
log "[6/8] Instalando Scipion 3.0..."
SCIPION_DIR="$PROJECT_DIR/SOFTWARE/scipion-3.0"
if [ ! -d "$SCIPION_DIR" ]; then
    cd "$PROJECT_DIR/SOFTWARE"
    # Descargar Scipion installer
    if [ ! -f "scipion3" ]; then
        wget -q https://scipion.i2pc.es/download_form/scipion3 -O scipion3
        chmod +x scipion3
    fi
    ./scipion3 install --prefix="$SCIPION_DIR"
    log "  Scipion instalado en $SCIPION_DIR"
else
    log "  Scipion ya existe en $SCIPION_DIR"
fi

# Instalar plugins
log "  Instalando plugins de Scipion..."
"$SCIPION_DIR/scipion3" installp -p scipion-em-flexutils 2>&1 | tail -3 | tee -a "$LOG_FILE" || true
"$SCIPION_DIR/scipion3" installp -p scipion-em-xmipp 2>&1 | tail -3 | tee -a "$LOG_FILE" || true

# -----------------------------------------------
# 7. Instalar Flexutils-Toolkit local
# -----------------------------------------------
log "[7/8] Instalando Flexutils-Toolkit..."
cd "$PROJECT_DIR/SOFTWARE/Flexutils-Toolkit"
pip install -e . 2>&1 | tail -3 | tee -a "$LOG_FILE"
cd "$PROJECT_DIR"

# -----------------------------------------------
# 8. Crear estructura de carpetas para resultados
# -----------------------------------------------
log "[8/8] Creando estructura de resultados..."
mkdir -p "$PROJECT_DIR/results"/{IgG-RL,MDSpike,Ribosome-80S,Spike-SARS2}/{hetsiren,cryodrgn,flexconsensus,figures}
mkdir -p "$PROJECT_DIR/data"/{cryobench,empiar_10028,empiar_10492}

log ""
log "=== SETUP COMPLETADO ==="
log "Siguiente paso: bash scripts/01_download_data.sh"
log ""
log "Resumen:"
log "  Entorno conda: flexconsensus"
log "  Scipion: $SCIPION_DIR"
log "  Resultados: $PROJECT_DIR/results/"
log "  Datos: $PROJECT_DIR/data/"
