# AWS Quick Start — FlexConsensus

## 1. Lanzar instancia EC2

```
AMI: Deep Learning AMI GPU PyTorch 2.1 (Ubuntu 22.04)
Instancia: g5.2xlarge (A10G 24GB, $1.21/h) o p3.2xlarge (V100 16GB, $3.06/h)
Almacenamiento: 800 GB gp3 (para los datasets EMPIAR)
```

## 2. Clonar y configurar

```bash
git clone <tu-repo> flexconsensus
cd flexconsensus

# Setup completo (instala conda, pytorch, tensorflow, scipion, etc.)
bash scripts/00_setup_aws.sh
conda activate flexconsensus
```

## 3. Ejecutar pipeline

### Opción A: Solo CryoBench (rápido, ~2-4h, ~5GB)
```bash
bash scripts/run_full_pipeline.sh --quick
```

### Opción B: Todo (incluye EMPIAR, ~24h+, ~600GB)
```bash
bash scripts/run_full_pipeline.sh --all
```

### Opción C: Paso a paso
```bash
# Descargar datos
bash scripts/01_download_data.sh --cryobench

# Preprocesar
python scripts/02_preprocess.py --dataset cryobench

# Ejecutar IAs (en paralelo si tienes 2+ GPUs)
python scripts/03_run_hetsiren.py --dataset IgG-RL --gpu 0
python scripts/04_run_cryodrgn.py --dataset IgG-RL --gpu 0

# FlexConsensus
python scripts/05_run_flexconsensus.py --dataset IgG-RL --gpu 0

# Validar y generar figuras
python scripts/06_validate.py --dataset IgG-RL
```

## 4. Mejoras (M1-M7)

```bash
# M1: 3DFlex como 3er método (requiere CryoSPARC)
python improvements/m1_3dflex.py --dataset IgG-RL --gpu 0

# M2: DynaMight como 4to método
python improvements/m2_dynamight.py --dataset IgG-RL --gpu 0

# M3: Proteína nueva (TRPV1, GroEL, etc.)
python improvements/m3_new_protein.py --protein trpv1 --gpu 0

# M4: Threshold automático (sin intervención manual)
python improvements/m4_auto_threshold.py --dataset IgG-RL

# M5: Explorar dimensiones > 3D
python improvements/m5_higher_dim.py --dataset IgG-RL --dims 2,3,4,5,6 --gpu 0

# M6: Validar con cristalografía PDB
python improvements/m6_crystal_validation.py --dataset IgG-RL --gpu 0

# M7: Optimizar hiperparámetros
python improvements/m7_hyperparam_search.py --dataset IgG-RL --mode quick --gpu 0
```

## 5. Ver resultados

```bash
# Figuras
ls results/IgG-RL/figures/

# Reportes JSON
cat results/IgG-RL/figures/validation_report_IgG-RL.json

# Webapp interactiva
cd webapp && python app.py
# Abrir http://localhost:5000
```

## Estructura de resultados

```
results/
├── IgG-RL/
│   ├── preprocessed/      ← Partículas procesadas
│   ├── hetsiren/          ← Espacio latente HetSIREN
│   ├── cryodrgn/          ← Espacio latente CryoDRGN
│   ├── flexconsensus/     ← Consensus space + errores
│   │   ├── consensus_latents.npy
│   │   ├── consensus_error.npy
│   │   ├── cluster_labels.npy
│   │   └── input_spaces/
│   └── figures/           ← Figuras del paper replicadas
│       ├── consensus_space_IgG-RL.png
│       ├── error_histogram_IgG-RL.png
│       ├── filtering_IgG-RL.png
│       └── validation_report_IgG-RL.json
├── MDSpike/
├── Ribosome-80S/
└── Spike-SARS2/
```
