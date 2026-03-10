#!/bin/bash
# Script automático de instalación - FlexConsensus
# NOTA: Ejecutar en Linux/WSL2 (Ubuntu)

set -e

echo "=== INSTALANDO FLEXCONSENSUS ==="

# 1. Instalar dependencias del sistema
echo "[1/6] Instalando dependencias del sistema..."
sudo apt-get update
sudo apt-get install -y python3-dev python3-pip python3-venv
sudo apt-get install -y build-essential cmake git wget

# 2. Crear entorno virtual Python
echo "[2/6] Creando entorno virtual..."
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install numpy matplotlib cryodrgn

# 3. Descargar Scipion
echo "[3/6] Descargando Scipion 3.0..."
if [ ! -d "SOFTWARE/scipion-3.0" ]; then
    cd SOFTWARE
    wget https://scipion.i2pc.es/downloads/scipion-3.0.tar.gz
    tar -xzf scipion-3.0.tar.gz
    cd scipion-3.0
    ./scipion install
    cd ../..
else
    echo "Scipion ya existe, saltando..."
fi

# 4. Instalar plugin Flexutils
echo "[4/6] Instalando plugin flexutils..."
cd SOFTWARE/scipion-3.0
./scipion installp -p scipion-em-flexutils
cd ../..

# 5. Verificar repos clonados
echo "[5/6] Verificando repositorios..."
for dir in SOFTWARE/scipion-em-flexutils SOFTWARE/Flexutils-Toolkit DATOS/CryoBench METODOS_IA/cryodrgn METODOS_IA/HetSIREN; do
    if [ -d "$dir" ]; then
        echo "  OK: $dir"
    else
        echo "  FALTA: $dir"
    fi
done

# 6. Mensaje final
echo ""
echo "=== INSTALACION COMPLETADA ==="
echo "Para ejecutar Scipion: cd SOFTWARE/scipion-3.0 && ./scipion run"
echo "Datos en: DATOS/CryoBench/"
echo "Scripts de visualizacion en: RESULTADOS/Visualizaciones/"
