#!/usr/bin/env python3
"""
FlexConsensus - FASE 3: Entrenar y ejecutar FlexConsensus
=========================================================
Entrena la red multi-autoencoder FlexConsensus que unifica los espacios
latentes de HetSIREN y CryoDRGN en un único consensus space.

Arquitectura (del paper):
  - Un encoder por cada espacio de entrada (1024-1024-1024-latent_dim)
  - Un decoder por cada espacio de entrada (latent_dim-1024-1024-1024-output_dim)
  - Loss: Representación + L1(distancia entre encoders) + L2(Shannon) + L3(Wasserstein)
  - Optimizer: Adam, lr=1e-5, batch_size=1024

Salida:
  - consensus_latents.npy: Espacio de consenso (N, latent_dim)
  - consensus_error.npy: Error de consenso por partícula (N,)
  - representation_error.npy: Error de representación (N,)

Uso:
  python scripts/05_run_flexconsensus.py --dataset IgG-RL --gpu 0
  python scripts/05_run_flexconsensus.py --dataset all --gpu 0
"""

import argparse
import os
import sys
import subprocess
import json
import glob
import numpy as np
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent
RESULTS_DIR = PROJECT_DIR / "results"
TOOLKIT_DIR = PROJECT_DIR / "SOFTWARE" / "Flexutils-Toolkit"

# Hiperparámetros FlexConsensus (del paper: Adam lr=1e-5, batch=1024)
FC_CONFIGS = {
    "IgG-RL": {
        "latent_dim": 3,       # Consensus space dimension (siempre 3 para visualización)
        "epochs": 100,
        "batch_size": 1024,
        "lr": 1e-5,
        "split_train": 0.8,
        "description": "IgG-RL: Consensus 3D, 2 métodos",
    },
    "MDSpike": {
        "latent_dim": 3,
        "epochs": 100,
        "batch_size": 1024,
        "lr": 1e-5,
        "split_train": 0.8,
        "description": "MDSpike: Consensus 3D, 2 métodos",
    },
    "Ribosome-80S": {
        "latent_dim": 3,
        "epochs": 100,
        "batch_size": 1024,
        "lr": 1e-5,
        "split_train": 0.8,
        "description": "Ribosome 80S: Consensus 3D, 2 métodos",
    },
    "Spike-SARS2": {
        "latent_dim": 3,
        "epochs": 100,
        "batch_size": 1024,
        "lr": 1e-5,
        "split_train": 0.8,
        "description": "Spike SARS-CoV-2: Consensus 3D, 2 métodos",
    },
}

ALL_DATASETS = ["IgG-RL", "MDSpike", "Ribosome-80S", "Spike-SARS2"]


def log(msg):
    print(f"[FLEXCONSENSUS] {msg}", flush=True)


def prepare_input_spaces(dataset_name):
    """
    Prepara los archivos .txt de espacios latentes para FlexConsensus.
    FlexConsensus espera un directorio con N archivos .txt, uno por método.
    """
    result_dir = RESULTS_DIR / dataset_name
    fc_input_dir = result_dir / "flexconsensus" / "input_spaces"
    fc_input_dir.mkdir(parents=True, exist_ok=True)

    methods_found = []

    # Espacio 1: HetSIREN
    hetsiren_latent = result_dir / "hetsiren" / "latent_space.txt"
    if hetsiren_latent.exists():
        dest = fc_input_dir / "space_hetsiren.txt"
        if not dest.exists():
            import shutil
            shutil.copy2(hetsiren_latent, dest)
        methods_found.append(("HetSIREN", dest))
        log(f"  Espacio HetSIREN: {np.loadtxt(dest).shape}")
    else:
        log(f"  WARNING: No se encontró espacio HetSIREN en {hetsiren_latent}")

    # Espacio 2: CryoDRGN
    cryodrgn_latent = result_dir / "cryodrgn" / "latent_space.txt"
    if cryodrgn_latent.exists():
        dest = fc_input_dir / "space_cryodrgn.txt"
        if not dest.exists():
            import shutil
            shutil.copy2(cryodrgn_latent, dest)
        methods_found.append(("CryoDRGN", dest))
        log(f"  Espacio CryoDRGN: {np.loadtxt(dest).shape}")
    else:
        log(f"  WARNING: No se encontró espacio CryoDRGN en {cryodrgn_latent}")

    # (Opcional) Espacio 3: 3DFlex (mejora M1)
    flex3d_latent = result_dir / "3dflex" / "latent_space.txt"
    if flex3d_latent.exists():
        dest = fc_input_dir / "space_3dflex.txt"
        if not dest.exists():
            import shutil
            shutil.copy2(flex3d_latent, dest)
        methods_found.append(("3DFlex", dest))
        log(f"  Espacio 3DFlex: {np.loadtxt(dest).shape}")

    # (Opcional) Espacio 4: DynaMight (mejora M2)
    dynamight_latent = result_dir / "dynamight" / "latent_space.txt"
    if dynamight_latent.exists():
        dest = fc_input_dir / "space_dynamight.txt"
        if not dest.exists():
            import shutil
            shutil.copy2(dynamight_latent, dest)
        methods_found.append(("DynaMight", dest))
        log(f"  Espacio DynaMight: {np.loadtxt(dest).shape}")

    # Verificar que todos los espacios tienen el mismo número de partículas
    if len(methods_found) >= 2:
        shapes = []
        for name, path in methods_found:
            data = np.loadtxt(path)
            shapes.append(data.shape[0])
        if len(set(shapes)) > 1:
            log(f"  ERROR: Los espacios tienen diferente número de partículas: {shapes}")
            log(f"  Todos deben tener exactamente las mismas N partículas")
            return None, 0
        log(f"  OK: {len(methods_found)} espacios, {shapes[0]} partículas cada uno")

    return fc_input_dir, len(methods_found)


def run_flexconsensus(dataset_name, gpu="0"):
    """Ejecuta FlexConsensus para un dataset."""
    config = FC_CONFIGS[dataset_name]
    result_dir = RESULTS_DIR / dataset_name
    fc_dir = result_dir / "flexconsensus"
    fc_dir.mkdir(parents=True, exist_ok=True)

    log(f"\n{'='*60}")
    log(f"FLEXCONSENSUS: {config['description']}")
    log(f"{'='*60}")

    # Verificar si ya completado
    consensus_output = fc_dir / "consensus_latents.npy"
    if consensus_output.exists():
        log(f"FlexConsensus ya completado para {dataset_name}. Saltando.")
        return True

    # Preparar espacios de entrada
    log("  Preparando espacios de entrada...")
    input_dir, n_methods = prepare_input_spaces(dataset_name)
    if n_methods < 2:
        log(f"  ERROR: Se necesitan al menos 2 métodos. Encontrados: {n_methods}")
        log(f"  Ejecuta primero scripts/03_run_hetsiren.py y scripts/04_run_cryodrgn.py")
        return False

    log(f"  Métodos encontrados: {n_methods}")

    # --- ENTRENAR FLEXCONSENSUS ---
    log(f"  Entrenando FlexConsensus (lat_dim={config['latent_dim']}, epochs={config['epochs']})...")

    train_script = TOOLKIT_DIR / "tensorflow_toolkit" / "scripts" / "train_flex_consensus.py"

    train_args = [
        sys.executable, str(train_script),
        "--data_path", str(input_dir),
        "--out_path", str(fc_dir),
        "--lat_dim", str(config["latent_dim"]),
        "--batch_size", str(config["batch_size"]),
        "--shuffle",
        "--split_train", str(config["split_train"]),
        "--lr", str(config["lr"]),
        "--epochs", str(config["epochs"]),
        "--tensorboard",
        "--gpu", str(gpu),
    ]

    log(f"  Entrenando ({config['epochs']} épocas, ~{config['epochs'] * 16}s estimados)...")
    env = os.environ.copy()
    env["CUDA_VISIBLE_DEVICES"] = gpu

    result = subprocess.run(train_args, capture_output=True, text=True, env=env)

    if result.returncode != 0:
        log(f"  ERROR en entrenamiento:")
        log(f"  {result.stderr[-500:]}")
        with open(fc_dir / "train_error.log", "w") as f:
            f.write(result.stdout + "\n" + result.stderr)
        return False

    log("  Entrenamiento completado!")

    # --- PREDECIR (generar consensus space) ---
    log("  Generando consensus space...")

    predict_script = TOOLKIT_DIR / "tensorflow_toolkit" / "scripts" / "predict_flex_consensus.py"
    weights_file = list(fc_dir.glob("network/flex_consensus_model*"))
    if not weights_file:
        weights_file = list(fc_dir.glob("network/*.h5"))
    if not weights_file:
        log("  ERROR: No se encontraron pesos del modelo")
        return False
    weights_file = str(weights_file[0])

    predict_args = [
        sys.executable, str(predict_script),
        "--data_path", str(input_dir),
        "--out_path", str(fc_dir),
        "--weigths_file", weights_file,
        "--lat_dim", str(config["latent_dim"]),
        "--gpu", str(gpu),
    ]

    result = subprocess.run(predict_args, capture_output=True, text=True, env=env)

    if result.returncode != 0:
        log(f"  ERROR en predicción: {result.stderr[-300:]}")
        return False

    # --- VERIFICAR SALIDAS ---
    outputs = {
        "consensus_latents.npy": "Espacio de consenso",
        "consensus_error.npy": "Error de consenso",
        "representation_error.npy": "Error de representación",
    }

    for filename, desc in outputs.items():
        filepath = fc_dir / filename
        if filepath.exists():
            data = np.load(filepath)
            log(f"  {desc}: {filename} (shape: {data.shape})")
        else:
            log(f"  WARNING: No se generó {filename}")

    # --- CLUSTERING DE CONFORMACIONES ---
    log("  Detectando conformaciones (K-Means)...")
    consensus = np.load(fc_dir / "consensus_latents.npy")

    # Usar find_optimal_clusters del toolkit si existe, si no, sklearn
    try:
        from sklearn.cluster import KMeans
        from sklearn.metrics import silhouette_score

        # Probar K=2 a K=10, elegir el mejor por silhouette
        best_k = 2
        best_score = -1
        for k in range(2, 11):
            km = KMeans(n_clusters=k, random_state=42, n_init=10)
            labels = km.fit_predict(consensus)
            score = silhouette_score(consensus, labels, sample_size=min(10000, len(consensus)))
            log(f"    K={k}: silhouette={score:.4f}")
            if score > best_score:
                best_score = score
                best_k = k

        log(f"  Mejor K: {best_k} (silhouette={best_score:.4f})")

        # Clustering final
        km = KMeans(n_clusters=best_k, random_state=42, n_init=20)
        labels = km.fit_predict(consensus)
        np.save(fc_dir / "cluster_labels.npy", labels)
        np.save(fc_dir / "cluster_centers.npy", km.cluster_centers_)

        # Estadísticas por cluster
        errors = np.load(fc_dir / "consensus_error.npy")
        log(f"\n  === Conformaciones detectadas: {best_k} ===")
        for i in range(best_k):
            mask = labels == i
            n = mask.sum()
            pct = 100 * n / len(labels)
            mean_err = errors[mask].mean()
            log(f"  Conf {i}: {n:,} partículas ({pct:.1f}%), error medio: {mean_err:.4f}")

    except ImportError:
        log("  WARNING: sklearn no disponible, saltando clustering")

    # Guardar metadatos
    run_meta = {
        "method": "FlexConsensus",
        "dataset": dataset_name,
        "config": config,
        "n_methods": n_methods,
        "n_conformations": best_k if 'best_k' in dir() else None,
        "weights_file": weights_file,
    }
    with open(fc_dir / "run_meta.json", "w") as f:
        json.dump(run_meta, f, indent=2, default=str)

    log(f"  FlexConsensus completado para {dataset_name}!")
    return True


# -----------------------------------------------
# Main
# -----------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="FASE 3: FlexConsensus")
    parser.add_argument("--dataset", required=True,
                        choices=ALL_DATASETS + ["all"],
                        help="Dataset a procesar")
    parser.add_argument("--gpu", default="0", help="GPU IDs (default: 0)")
    args = parser.parse_args()

    datasets = ALL_DATASETS if args.dataset == "all" else [args.dataset]

    results = {}
    for ds in datasets:
        ok = run_flexconsensus(ds, args.gpu)
        results[ds] = "OK" if ok else "FAILED"

    log("\n=== RESUMEN FLEXCONSENSUS ===")
    for name, status in results.items():
        log(f"  {name}: {status}")

    log("\nSiguiente paso: python scripts/06_validate.py --dataset ...")


if __name__ == "__main__":
    main()
