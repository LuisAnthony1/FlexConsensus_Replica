#!/bin/bash
# ==============================================================================
# FlexConsensus - Pipeline Completo
# ==============================================================================
# Ejecuta todas las fases del pipeline secuencialmente.
#
# Uso:
#   bash scripts/run_full_pipeline.sh              # Todo, todos los datasets
#   bash scripts/run_full_pipeline.sh --quick       # Solo CryoBench (rápido)
#   bash scripts/run_full_pipeline.sh --dataset IgG-RL  # Un dataset específico
#
# Requiere: GPU + conda activate flexconsensus
# Tiempo estimado:
#   CryoBench (IgG-RL + MDSpike): ~2-4 horas
#   EMPIAR-10028 (Ribosome 80S): ~8-12 horas
#   EMPIAR-10492 (Spike SARS-CoV-2): ~12-24 horas
# ==============================================================================

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
LOG_FILE="$PROJECT_DIR/pipeline.log"
GPU="${GPU:-0}"

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"; }

# Parse args
MODE="all"
DATASET_FLAG=""
if [ "${1:-}" == "--quick" ]; then
    MODE="quick"
elif [ "${1:-}" == "--dataset" ]; then
    MODE="single"
    DATASET_FLAG="${2:?ERROR: Especifica un dataset (IgG-RL, MDSpike, Ribosome-80S, Spike-SARS2)}"
fi

log "=========================================="
log "FLEXCONSENSUS PIPELINE"
log "Mode: $MODE"
log "GPU: $GPU"
log "=========================================="

# Verificar entorno
if ! python -c "import torch; assert torch.cuda.is_available()" 2>/dev/null; then
    log "WARNING: CUDA no disponible. El pipeline será MUY lento sin GPU."
fi

# -----------------------------------------------
# Determinar datasets a procesar
# -----------------------------------------------
if [ "$MODE" == "quick" ]; then
    DATASETS=("IgG-RL" "MDSpike")
    DOWNLOAD_FLAG="--cryobench"
elif [ "$MODE" == "single" ]; then
    DATASETS=("$DATASET_FLAG")
    case $DATASET_FLAG in
        IgG-RL|MDSpike) DOWNLOAD_FLAG="--cryobench" ;;
        Ribosome-80S)   DOWNLOAD_FLAG="--empiar10028" ;;
        Spike-SARS2)    DOWNLOAD_FLAG="--empiar10492" ;;
        *) log "ERROR: Dataset desconocido: $DATASET_FLAG"; exit 1 ;;
    esac
else
    DATASETS=("IgG-RL" "MDSpike" "Ribosome-80S" "Spike-SARS2")
    DOWNLOAD_FLAG="--all"
fi

log "Datasets: ${DATASETS[*]}"
TOTAL_STEPS=$((4 * ${#DATASETS[@]}))
CURRENT_STEP=0

report_progress() {
    CURRENT_STEP=$((CURRENT_STEP + 1))
    PCT=$((100 * CURRENT_STEP / TOTAL_STEPS))
    log "[$CURRENT_STEP/$TOTAL_STEPS] ($PCT%) $1"
}

# -----------------------------------------------
# FASE 0: Descargar datos (si no existen)
# -----------------------------------------------
log ""
log "=== FASE 0: DESCARGA DE DATOS ==="
bash "$SCRIPT_DIR/01_download_data.sh" $DOWNLOAD_FLAG 2>&1 | tee -a "$LOG_FILE"

# -----------------------------------------------
# Ejecutar pipeline por dataset
# -----------------------------------------------
RESULTS=()
for DS in "${DATASETS[@]}"; do
    log ""
    log "############################################"
    log "# PROCESANDO: $DS"
    log "############################################"

    DS_START=$(date +%s)

    # Determinar flag para scripts python
    case $DS in
        IgG-RL|MDSpike) PY_FLAG="cryobench" ;;
        Ribosome-80S)   PY_FLAG="empiar10028" ;;
        Spike-SARS2)    PY_FLAG="empiar10492" ;;
    esac

    # FASE 1: Preprocesamiento
    report_progress "$DS — FASE 1: Preprocesamiento"
    python "$SCRIPT_DIR/02_preprocess.py" --dataset "$PY_FLAG" 2>&1 | tee -a "$LOG_FILE"

    # FASE 2a: HetSIREN
    report_progress "$DS — FASE 2a: HetSIREN"
    python "$SCRIPT_DIR/03_run_hetsiren.py" --dataset "$DS" --gpu "$GPU" 2>&1 | tee -a "$LOG_FILE"

    # FASE 2b: CryoDRGN
    report_progress "$DS — FASE 2b: CryoDRGN"
    python "$SCRIPT_DIR/04_run_cryodrgn.py" --dataset "$DS" --gpu "$GPU" 2>&1 | tee -a "$LOG_FILE"

    # FASE 3: FlexConsensus
    report_progress "$DS — FASE 3: FlexConsensus"
    python "$SCRIPT_DIR/05_run_flexconsensus.py" --dataset "$DS" --gpu "$GPU" 2>&1 | tee -a "$LOG_FILE"

    # Tiempo
    DS_END=$(date +%s)
    DS_DURATION=$(( (DS_END - DS_START) / 60 ))
    RESULTS+=("$DS: ${DS_DURATION}min")
    log "$DS completado en ${DS_DURATION} minutos"
done

# -----------------------------------------------
# FASE 4: Validación de todos los datasets
# -----------------------------------------------
log ""
log "=== FASE 4: VALIDACIÓN Y FIGURAS ==="
python "$SCRIPT_DIR/06_validate.py" --dataset all 2>&1 | tee -a "$LOG_FILE"

# -----------------------------------------------
# Resumen final
# -----------------------------------------------
log ""
log "=========================================="
log "PIPELINE COMPLETADO"
log "=========================================="
log ""
log "Tiempos por dataset:"
for r in "${RESULTS[@]}"; do
    log "  $r"
done
log ""
log "Resultados en:"
log "  $PROJECT_DIR/results/"
log ""
log "Figuras en:"
for DS in "${DATASETS[@]}"; do
    FIGS=$(find "$PROJECT_DIR/results/$DS/figures" -name "*.png" 2>/dev/null | wc -l)
    log "  results/$DS/figures/ ($FIGS figuras)"
done
log ""
log "Webapp (para visualizar interactivamente):"
log "  cd webapp && python app.py"
log ""
log "Log completo: $LOG_FILE"
