#!/bin/bash
# ==============================================================================
# FlexConsensus - Actualizar servidor después de git push
# ==============================================================================
# Uso (en el servidor EC2):
#   bash flexconsensus/deploy/update_server.sh
# ==============================================================================

set -euo pipefail

PROJECT_DIR="/home/ubuntu/flexconsensus"

echo "=== ACTUALIZANDO FLEXCONSENSUS ==="

cd "$PROJECT_DIR"
git pull origin main

echo "Reiniciando Flask..."
sudo systemctl restart flexconsensus

echo ""
echo "=== ACTUALIZADO ==="
echo "Verifica en: http://$(curl -s http://169.254.169.254/latest/meta-data/public-ipv4 2>/dev/null)/flexconsensus/"
