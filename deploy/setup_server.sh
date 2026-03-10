#!/bin/bash
# ==============================================================================
# FlexConsensus - Deploy en EC2 Ubuntu con Apache
# ==============================================================================
# Ejecutar en el servidor EC2 (misma instancia que ecoli_k12_analysis)
#
# Uso:
#   ssh -i tu-clave.pem ubuntu@TU-IP
#   cd /home/ubuntu
#   git clone https://github.com/LuisAnthony1/FlexConsensus_Replica.git flexconsensus
#   bash flexconsensus/deploy/setup_server.sh
# ==============================================================================

set -euo pipefail

PROJECT_DIR="/home/ubuntu/flexconsensus"
WEBAPP_DIR="$PROJECT_DIR/webapp"

echo "=== DEPLOY FLEXCONSENSUS EN EC2 ==="

# -----------------------------------------------
# 1. Instalar dependencias del sistema
# -----------------------------------------------
echo "[1/6] Instalando dependencias..."
sudo apt-get update -qq
sudo apt-get install -y -qq python3-pip python3-venv apache2 libapache2-mod-proxy-html

# -----------------------------------------------
# 2. Crear entorno virtual Python
# -----------------------------------------------
echo "[2/6] Creando entorno virtual..."
cd "$WEBAPP_DIR"
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install flask gunicorn numpy requests

# -----------------------------------------------
# 3. Crear servicio systemd para Flask
# -----------------------------------------------
echo "[3/6] Configurando servicio systemd..."
sudo tee /etc/systemd/system/flexconsensus.service > /dev/null <<SERVICEEOF
[Unit]
Description=FlexConsensus Flask App
After=network.target

[Service]
User=ubuntu
Group=ubuntu
WorkingDirectory=$WEBAPP_DIR
Environment="PATH=$WEBAPP_DIR/venv/bin"
ExecStart=$WEBAPP_DIR/venv/bin/gunicorn --workers 2 --bind 127.0.0.1:5000 app:app
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
SERVICEEOF

sudo systemctl daemon-reload
sudo systemctl enable flexconsensus
sudo systemctl start flexconsensus

echo "  Flask corriendo en puerto 5000"

# -----------------------------------------------
# 4. Configurar Apache como reverse proxy
# -----------------------------------------------
echo "[4/6] Configurando Apache..."

# Habilitar módulos necesarios
sudo a2enmod proxy proxy_http proxy_balancer lbmethod_byrequests headers

# Crear configuración de Apache para FlexConsensus
sudo tee /etc/apache2/sites-available/flexconsensus.conf > /dev/null <<APACHEEOF
<VirtualHost *:80>
    # Si ya tienes ecoli en el mismo puerto, usamos Location
    # FlexConsensus estará en http://TU-IP/flexconsensus/

    # Proxy para la app Flask
    ProxyPreserveHost On

    # Ruta /flexconsensus/ -> Flask en puerto 5000
    ProxyPass /flexconsensus/ http://127.0.0.1:5000/
    ProxyPassReverse /flexconsensus/ http://127.0.0.1:5000/

    # Headers
    RequestHeader set X-Forwarded-Proto "http"
    RequestHeader set X-Script-Name "/flexconsensus"
</VirtualHost>
APACHEEOF

# Si ya hay un default site, agregar las líneas de proxy ahí
if [ -f /etc/apache2/sites-enabled/000-default.conf ]; then
    echo "  Agregando proxy a la config existente de Apache..."
    # Verificar si ya tiene la config de flexconsensus
    if ! grep -q "flexconsensus" /etc/apache2/sites-enabled/000-default.conf; then
        # Agregar antes del </VirtualHost> final
        sudo sed -i '/<\/VirtualHost>/i \
    # === FlexConsensus ===\
    ProxyPreserveHost On\
    ProxyPass /flexconsensus/ http://127.0.0.1:5000/\
    ProxyPassReverse /flexconsensus/ http://127.0.0.1:5000/' /etc/apache2/sites-enabled/000-default.conf
    fi
else
    sudo a2ensite flexconsensus
fi

# -----------------------------------------------
# 5. Reiniciar Apache
# -----------------------------------------------
echo "[5/6] Reiniciando Apache..."
sudo systemctl restart apache2

# -----------------------------------------------
# 6. Verificar
# -----------------------------------------------
echo "[6/6] Verificando..."

# Flask
if curl -s http://127.0.0.1:5000/ > /dev/null 2>&1; then
    echo "  ✓ Flask corriendo en puerto 5000"
else
    echo "  ✗ Flask NO responde. Revisar: sudo journalctl -u flexconsensus"
fi

# Apache
if curl -s http://127.0.0.1/flexconsensus/ > /dev/null 2>&1; then
    echo "  ✓ Apache proxy funcionando"
else
    echo "  ✗ Apache proxy NO funciona. Revisar: sudo journalctl -u apache2"
fi

# IP pública
PUBLIC_IP=$(curl -s http://169.254.169.254/latest/meta-data/public-ipv4 2>/dev/null || echo "NO-DETECTADA")

echo ""
echo "=== DEPLOY COMPLETADO ==="
echo ""
echo "URLs:"
echo "  E. coli:        http://$PUBLIC_IP/"
echo "  FlexConsensus:  http://$PUBLIC_IP/flexconsensus/"
echo ""
echo "Comandos útiles:"
echo "  Ver logs Flask:    sudo journalctl -u flexconsensus -f"
echo "  Reiniciar Flask:   sudo systemctl restart flexconsensus"
echo "  Ver logs Apache:   sudo tail -f /var/log/apache2/error.log"
echo "  Status:            sudo systemctl status flexconsensus"
