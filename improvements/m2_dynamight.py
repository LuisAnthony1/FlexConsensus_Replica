#!/usr/bin/env python3
"""
Mejora M2: Agregar DynaMight como cuarto método
=================================================
Integra DynaMight para consenso más robusto con 4 métodos simultáneos.

DynaMight modela heterogeneidad conformacional usando Gaussian Mixture Models
sobre deformaciones 3D, aprendiendo modos de movimiento de forma no supervisada.

Referencia: Schwab et al., "DynaMight: estimating molecular motions with
improved reconstruction from cryo-EM images", Nature Methods 2024.

Requiere: pip install dynamight

Uso:
  python improvements/m2_dynamight.py --dataset IgG-RL --gpu 0
"""

import argparse
import os
import sys
import json
import subprocess
import numpy as np
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent
RESULTS_DIR = PROJECT_DIR / "results"

DYNAMIGHT_CONFIGS = {
    "IgG-RL": {
        "n_modes": 4,
        "epochs": 50,
        "batch_size": 32,
        "description": "IgG-RL: DynaMight 4 modos",
    },
    "MDSpike": {
        "n_modes": 8,
        "epochs": 50,
        "batch_size": 32,
        "description": "MDSpike: DynaMight 8 modos",
    },
    "Ribosome-80S": {
        "n_modes": 10,
        "epochs": 30,
        "batch_size": 32,
        "description": "Ribosome: DynaMight 10 modos",
    },
    "Spike-SARS2": {
        "n_modes": 10,
        "epochs": 30,
        "batch_size": 32,
        "description": "Spike: DynaMight 10 modos",
    },
}


def log(msg):
    print(f"[DYNAMIGHT] {msg}", flush=True)


def install_dynamight():
    """Instala DynaMight si no está disponible."""
    try:
        import dynamight
        log(f"  DynaMight ya instalado: {dynamight.__version__}")
        return True
    except ImportError:
        log("  Instalando DynaMight...")
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", "dynamight"],
            capture_output=True, text=True,
        )
        if result.returncode != 0:
            # Intentar desde GitHub
            log("  pip install falló, intentando desde GitHub...")
            result = subprocess.run(
                [sys.executable, "-m", "pip", "install",
                 "git+https://github.com/schwab-lab/DynaMight.git"],
                capture_output=True, text=True,
            )
        return result.returncode == 0


def run_dynamight(dataset_name, gpu="0"):
    """Ejecuta DynaMight para un dataset."""
    config = DYNAMIGHT_CONFIGS[dataset_name]
    result_dir = RESULTS_DIR / dataset_name
    dm_dir = result_dir / "dynamight"
    dm_dir.mkdir(parents=True, exist_ok=True)

    log(f"\n{'='*60}")
    log(f"DYNAMIGHT: {config['description']}")
    log(f"{'='*60}")

    # Verificar si ya completado
    latent_output = dm_dir / "latent_space.txt"
    if latent_output.exists():
        log(f"DynaMight ya completado para {dataset_name}. Saltando.")
        return True

    # Verificar preprocesamiento
    preproc_dir = result_dir / "preprocessed"
    meta_file = preproc_dir / "preprocess_meta.json"
    if not meta_file.exists():
        log(f"ERROR: Ejecuta primero scripts/02_preprocess.py")
        return False

    # Buscar partículas
    particles_mrcs = list(preproc_dir.glob("particles_*.mrcs"))
    if not particles_mrcs:
        log("ERROR: No se encontraron partículas")
        return False
    particles_mrcs = str(particles_mrcs[0])

    poses_pkl = preproc_dir / "poses.pkl"
    with open(meta_file) as f:
        meta = json.load(f)
    pixel_size = meta.get("pixel_size", 1.0)

    # Instalar DynaMight
    if not install_dynamight():
        log("ERROR: No se pudo instalar DynaMight")
        return False

    # --- EJECUTAR DYNAMIGHT ---
    env = os.environ.copy()
    env["CUDA_VISIBLE_DEVICES"] = gpu

    # DynaMight usa su propio CLI
    # Paso 1: Preparar datos
    log("  Preparando datos para DynaMight...")
    prep_cmd = [
        sys.executable, "-m", "dynamight.prepare",
        "--particles", particles_mrcs,
        "--poses", str(poses_pkl),
        "--output", str(dm_dir / "prepared"),
        "--pixel-size", str(pixel_size),
    ]

    result = subprocess.run(prep_cmd, capture_output=True, text=True, env=env)
    if result.returncode != 0:
        log(f"  Preparación falló, intentando método alternativo...")
        # Método alternativo: usar API directa
        return run_dynamight_direct(dataset_name, config, dm_dir, particles_mrcs, poses_pkl, pixel_size, gpu)

    # Paso 2: Entrenar modelo
    log(f"  Entrenando DynaMight (n_modes={config['n_modes']}, epochs={config['epochs']})...")
    train_cmd = [
        sys.executable, "-m", "dynamight.train",
        "--prepared-data", str(dm_dir / "prepared"),
        "--output", str(dm_dir / "model"),
        "--n-modes", str(config["n_modes"]),
        "--epochs", str(config["epochs"]),
        "--batch-size", str(config["batch_size"]),
    ]

    result = subprocess.run(train_cmd, capture_output=True, text=True, env=env)
    if result.returncode != 0:
        log(f"  ERROR entrenando DynaMight: {result.stderr[-300:]}")
        return False

    # Paso 3: Extraer espacio latente
    log("  Extrayendo espacio latente...")
    predict_cmd = [
        sys.executable, "-m", "dynamight.predict",
        "--model", str(dm_dir / "model"),
        "--prepared-data", str(dm_dir / "prepared"),
        "--output", str(dm_dir / "predictions"),
    ]

    result = subprocess.run(predict_cmd, capture_output=True, text=True, env=env)
    if result.returncode != 0:
        log(f"  ERROR en predicción: {result.stderr[-300:]}")
        return False

    # Buscar archivo de espacio latente generado por DynaMight
    latent_files = list((dm_dir / "predictions").glob("*latent*"))
    latent_files += list((dm_dir / "predictions").glob("*coefficients*"))
    latent_files += list((dm_dir / "predictions").glob("*.npy"))

    if latent_files:
        latent_data = np.load(str(latent_files[0]))
        np.savetxt(latent_output, latent_data, fmt="%.8f")
        log(f"  Espacio latente: {latent_output} (shape: {latent_data.shape})")
    else:
        log("  WARNING: No se encontró espacio latente automáticamente")
        return False

    # Metadatos
    run_meta = {
        "method": "DynaMight",
        "dataset": dataset_name,
        "config": config,
        "latent_shape": list(latent_data.shape),
    }
    with open(dm_dir / "run_meta.json", "w") as f:
        json.dump(run_meta, f, indent=2)

    log(f"  DynaMight completado para {dataset_name}!")
    return True


def run_dynamight_direct(dataset_name, config, dm_dir, particles_mrcs, poses_pkl, pixel_size, gpu):
    """
    Ejecuta DynaMight usando la API Python directamente cuando el CLI no está disponible.
    """
    log("  Usando API directa de DynaMight...")

    try:
        import pickle
        import torch
        from scipy.spatial.transform import Rotation as R

        # Cargar poses
        with open(poses_pkl, "rb") as f:
            rotations = pickle.load(f)
            translations = pickle.load(f)

        # Cargar partículas como memmapped array
        import mrcfile
        with mrcfile.mmap(particles_mrcs, mode="r") as mrc:
            n_particles = mrc.data.shape[0]
            box_size = mrc.data.shape[1]

        log(f"  Partículas: {n_particles}, box: {box_size}px")

        # Intentar importar DynaMight core
        try:
            from dynamight.models import DeformationModel
            from dynamight.data import ParticleDataset

            dataset = ParticleDataset(
                particles_mrcs,
                rotations=rotations,
                translations=translations,
                pixel_size=pixel_size,
            )

            model = DeformationModel(
                box_size=box_size,
                n_modes=config["n_modes"],
            ).cuda()

            # Training loop simplificado
            optimizer = torch.optim.Adam(model.parameters(), lr=1e-4)
            dataloader = torch.utils.data.DataLoader(
                dataset, batch_size=config["batch_size"], shuffle=True,
            )

            for epoch in range(config["epochs"]):
                epoch_loss = 0
                for batch in dataloader:
                    optimizer.zero_grad()
                    loss = model.training_step(batch)
                    loss.backward()
                    optimizer.step()
                    epoch_loss += loss.item()

                if (epoch + 1) % 10 == 0:
                    log(f"    Epoch {epoch+1}/{config['epochs']}, loss: {epoch_loss/len(dataloader):.4f}")

            # Extraer espacio latente
            latent_data = model.encode_all(dataset)
            latent_output = dm_dir / "latent_space.txt"
            np.savetxt(latent_output, latent_data, fmt="%.8f")
            log(f"  Espacio latente: {latent_output} (shape: {latent_data.shape})")
            return True

        except ImportError as e:
            log(f"  DynaMight API no disponible: {e}")
            log("  Generando script para ejecución manual...")

            # Generar script que el usuario puede ejecutar
            script = dm_dir / "run_dynamight_manual.sh"
            with open(script, "w") as f:
                f.write(f"""#!/bin/bash
# Ejecutar DynaMight manualmente
# Instalar: pip install dynamight
# Referencia: https://github.com/schwab-lab/DynaMight

CUDA_VISIBLE_DEVICES={gpu} python -c "
import dynamight
# ... seguir documentación de DynaMight
# Guardar resultado en: {dm_dir / 'latent_space.txt'}
"
""")
            log(f"  Script generado: {script}")
            return False

    except Exception as e:
        log(f"  ERROR: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description="M2: DynaMight como cuarto método")
    parser.add_argument("--dataset", required=True,
                        choices=list(DYNAMIGHT_CONFIGS.keys()) + ["all"])
    parser.add_argument("--gpu", default="0")
    args = parser.parse_args()

    datasets = list(DYNAMIGHT_CONFIGS.keys()) if args.dataset == "all" else [args.dataset]
    for ds in datasets:
        run_dynamight(ds, args.gpu)


if __name__ == "__main__":
    main()
