# 🧬 FlexConsensus — Replicación y Mejora
> Basado en: *"Merging conformational landscapes in a single consensus space with FlexConsensus algorithm"*  
> Nature Methods, Volume 22, October 2025 | DOI: 10.1038/s41592-025-02841-w  
> Autores: David Herreros, Carlos Perez Mata, Carlos Oscar Sanchez Sorzano, Jose Maria Carazo

---

## 📌 Objetivo del Proyecto

Replicar al 100% el algoritmo FlexConsensus publicado en Nature Methods 2025, sustituyendo el único dataset no público (SARS-CoV-2 D614G) por un equivalente público, e implementar mejoras sobre la investigación original.

---

## 🗂️ Estructura del Proyecto

```
flexconsensus-replication/
│
├── README.md                  ← Este archivo
├── environment.yml            ← Dependencias del entorno
├── data/                      ← Datasets descargados
│   ├── cryobench/             ← IgG-RL y MDSpike
│   ├── empiar_10028/          ← Ribosome 80S
│   └── empiar_10492/          ← SARS-CoV-2 spike (reemplazo D614G)
├── scripts/                   ← Scripts de preprocesamiento
├── results/                   ← Resultados y figuras generadas
└── improvements/              ← Código de mejoras implementadas
```

---

## ⚙️ Requisitos de Sistema

| Componente | Mínimo | Recomendado |
|---|---|---|
| GPU | RTX 3080 (10GB VRAM) | RTX 3090 / 4090 |
| RAM | 32 GB | 64 GB |
| Almacenamiento | 500 GB | 1 TB SSD |
| OS | Ubuntu 20.04+ | Ubuntu 22.04 |
| Python | 3.8+ | 3.10 |

---

## 🔧 Instalación

### 1. Instalar Scipion 3.0
```bash
# Descargar instalador de Scipion
wget https://scipion.i2pc.es/download_form/scipion3
chmod +x scipion3
./scipion3 install
```

### 2. Instalar Plugin FlexConsensus
```bash
# Dentro de Scipion
scipion3 installp -p scipion-em-flexutils
```

### 3. Instalar Flexutils-Toolkit
```bash
pip install flexutils-toolkit
# o desde GitHub
git clone https://github.com/I2PC/Flexutils-Toolkit
cd Flexutils-Toolkit
pip install -e .
```

### 4. Instalar dependencias adicionales
```bash
pip install cryodrgn==3.4.0
# CryoSPARC 4.5.1 (requiere licencia académica gratuita)
# RELION 4.0
# Xmipp 3.24.12.0
```

---

## 📥 Descarga de Datasets

### Dataset 1: CryoBench (IgG-RL + MDSpike)
```bash
# Descargar desde CryoBench
git clone https://github.com/compSPI/CryoBench
cd CryoBench
# Seguir instrucciones de descarga del repo
# URL: https://cryobench.cs.princeton.edu/
```

### Dataset 2: EMPIAR-10028 (Ribosome 80S)
```bash
# Descargar via EMPIAR
# URL: https://www.ebi.ac.uk/empiar/EMPIAR-10028/
aspera -v -P33001 -i ~/.aspera/connect/etc/asperaweb_id_dsa.openssh \
  era-fasp@fasp.ebi.ac.uk:/empiar/world_availability/10028/ ./data/empiar_10028/
```

### Dataset 3: EMPIAR-10492 (SARS-CoV-2 Spike — reemplazo de D614G)
```bash
# URL: https://www.ebi.ac.uk/empiar/EMPIAR-10492/
aspera -v -P33001 -i ~/.aspera/connect/etc/asperaweb_id_dsa.openssh \
  era-fasp@fasp.ebi.ac.uk:/empiar/world_availability/10492/ ./data/empiar_10492/
```

> **¿Por qué EMPIAR-10492?**  
> Es el spike SARS-CoV-2 original (no D614G), misma proteína, mismos estados conformacionales three-down/one-up/two-up. Permite replicar Figs. 4-5 del paper con datos públicos.

---

## 🔬 Pipeline de Replicación

### FASE 1 — Preprocesamiento (igual al paper)
```
Scipion 3.0
  └── Importar partículas
  └── Estimar CTF (CryoSPARC)
  └── Alineamiento de partículas
  └── Consenso de alineamientos
```

### FASE 2 — Estimación de paisajes conformacionales
```
Para cada dataset:
  ├── Correr HetSIREN (modo reconstrucción)
  ├── Correr HetSIREN (modo refinamiento)  [solo EMPIAR-10028]
  └── Correr CryoDRGN v3.4.0
```

### FASE 3 — FlexConsensus
```
Inputs: espacios conformacionales de FASE 2
  └── Entrenar red multi-autoencoder
  └── Generar consensus space (3 dimensiones)
  └── Calcular consensus error por partícula
  └── Aplicar filtro estadístico (permutation test, P < 0.05)
  └── Generar figuras y métricas
```

### FASE 4 — Validación
```
  └── Comparar con figuras originales del paper
  └── Verificar poblaciones conformacionales
  └── Test de Mantel para correlación espacial
```

---

## 🏗️ Arquitectura de la Red (para implementación desde cero)

```python
# Multi-autoencoder FlexConsensus
# Por cada espacio de entrada N:

Encoder_N:
  - FC(input_dim, 1024) + ReLU
  - FC(1024, 1024) + ReLU  
  - FC(1024, 1024) + ReLU
  - FC(1024, latent_dim) + Linear  ← consensus space

Decoder_N:
  - FC(latent_dim, 1024) + ReLU
  - FC(1024, 1024) + ReLU
  - FC(1024, 1024) + ReLU
  - FC(1024, input_dim) + Linear

Optimizer: Adam, lr=1e-5, batch_size=1024
```

### Función de pérdida total:
```
L = Representación + L1 (distancia entre encoders) 
                   + L2 (Shannon mapping) 
                   + L3 (Wasserstein entre distribuciones)
```

---

## 🚀 Mejoras a Implementar

| # | Mejora | Descripción | Prioridad |
|---|---|---|---|
| M1 | Agregar 3DFlex como tercer método | Comparar 3 métodos simultáneos en vez de 2 | 🔴 Alta |
| M2 | Agregar DynaMight | Cuarto método para consenso más robusto | 🔴 Alta |
| M3 | Proteína nueva no estudiada | Aplicar a proteína farmacológicamente relevante | 🔴 Alta |
| M4 | Automatizar threshold | Selección automática sin intervención manual | 🟡 Media |
| M5 | Consensus space > 3D | Explorar 4-5 dimensiones latentes | 🟡 Media |
| M6 | Validación con cristalografía | Comparar con estructuras PDB conocidas | 🟡 Media |
| M7 | Optimización de hiperparámetros | Grid search sobre lr, batch_size, capas | 🟢 Baja |
| M8 | Interfaz web de visualización | Dashboard interactivo de resultados | 🟢 Baja |

---

## 📊 Resultados Esperados

| Figura del paper | Dataset usado | Estado |
|---|---|---|
| Fig. 1 (IgG-RL consensus) | CryoBench IgG-RL | ⏳ Pendiente |
| Fig. 2 (MDSpike consensus) | CryoBench MDSpike | ⏳ Pendiente |
| Fig. 3 (Ribosome consensus) | EMPIAR-10028 | ⏳ Pendiente |
| Fig. 4 (Spike consensus) | **EMPIAR-10492** (reemplazo) | ⏳ Pendiente |
| Fig. 5 (Spike filtrado) | **EMPIAR-10492** (reemplazo) | ⏳ Pendiente |

---

## 🔗 Links Importantes

| Recurso | URL |
|---|---|
| Paper Nature Methods | https://www.nature.com/articles/s41592-025-02841-w |
| Paper PubMed (gratis) | https://pmc.ncbi.nlm.nih.gov/articles/PMC12510870/ |
| Código Plugin GitHub | https://github.com/scipion-em/scipion-em-flexutils |
| Código Toolkit GitHub | https://github.com/I2PC/Flexutils-Toolkit |
| Plataforma Scipion | https://scipion.i2pc.es/ |
| Datos CryoBench | https://github.com/compSPI/CryoBench |
| Datos EMPIAR | https://www.ebi.ac.uk/empiar/ |
| Tutorial oficial | https://scipion-em.github.io/docs/release-3.0.0/docs/user/tutorials/flexibilityHub/main_page.html |
| Workflow interactivo | https://scipion.i2pc.es/cryoemworkflowviewer/workflow/aac223841371a67510e9eab16ac8870246b30d68 |

---

## 📧 Contacto del equipo original

- **David Herreros** (autor principal): dherreros@cnb.csic.es
- **Institución**: Centro Nacional de Biotecnología-CSIC, Madrid, España

> Para solicitar el dataset D614G original contactar también al laboratorio de **Sriram Subramanian**, University of British Columbia.

---

## 📝 Notas para el Programador

1. **Empezar por** instalar Scipion y correr el workflow interactivo de ejemplo antes de tocar código.
2. **El dataset más fácil** para probar que todo funciona es CryoBench IgG-RL — es pequeño y tiene ground truth.
3. **EMPIAR-10492 es grande** (~500GB), planificar almacenamiento antes de descargar.
4. **Las mejoras M1 y M2** (agregar 3DFlex y DynaMight) son las de mayor impacto científico y relativamente directas porque Scipion ya los integra.
5. **El training** toma ~16 segundos/época en RTX Ada 6000. En RTX 3090 estimar ~25-30 segundos/época.

---

*README generado para el proyecto de replicación y mejora de FlexConsensus — 2025*