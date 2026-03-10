#!/usr/bin/env python3
"""
FlexConsensus - FASE 2b: Ejecutar CryoDRGN
============================================
Entrena CryoDRGN v3.4 en cada dataset para generar el segundo espacio latente.

CryoDRGN usa un Variational Autoencoder (VAE) que trabaja en espacio de Fourier
para reconstruir volúmenes heterogéneos.

Salida: Espacio latente de CryoDRGN como .txt para FlexConsensus

Uso:
  python scripts/04_run_cryodrgn.py --dataset IgG-RL --gpu 0
  python scripts/04_run_cryodrgn.py --dataset all --gpu 0
"""

import argparse
import os
import sys
import subprocess
import json
import pickle
import glob
import numpy as np
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent
RESULTS_DIR = PROJECT_DIR / "results"

# Hiperparámetros por dataset (replicando el paper)
CRYODRGN_CONFIGS = {
    "IgG-RL": {
        "zdim": 4,           # Debe coincidir con HetSIREN para comparar
        "epochs": 25,
        "batch_size": 16,
        "lr": 1e-4,
        "enc_layers": 3,
        "enc_dim": 1024,
        "dec_layers": 3,
        "dec_dim": 1024,
        "encode_mode": "resid",
        "description": "IgG-RL: 4D latent, VAE en Fourier",
    },
    "MDSpike": {
        "zdim": 8,
        "epochs": 25,
        "batch_size": 16,
        "lr": 1e-4,
        "enc_layers": 3,
        "enc_dim": 1024,
        "dec_layers": 3,
        "dec_dim": 1024,
        "encode_mode": "resid",
        "description": "MDSpike: 8D latent, VAE en Fourier",
    },
    "Ribosome-80S": {
        "zdim": 10,
        "epochs": 25,
        "batch_size": 16,
        "lr": 1e-4,
        "enc_layers": 3,
        "enc_dim": 1024,
        "dec_layers": 3,
        "dec_dim": 1024,
        "encode_mode": "resid",
        "description": "Ribosome 80S: 10D latent, datos reales",
    },
    "Spike-SARS2": {
        "zdim": 10,
        "epochs": 25,
        "batch_size": 16,
        "lr": 1e-4,
        "enc_layers": 3,
        "enc_dim": 1024,
        "dec_layers": 3,
        "dec_dim": 1024,
        "encode_mode": "resid",
        "description": "Spike SARS-CoV-2: 10D latent, reemplazo D614G",
    },
}

ALL_DATASETS = ["IgG-RL", "MDSpike", "Ribosome-80S", "Spike-SARS2"]


def log(msg):
    print(f"[CRYODRGN] {msg}", flush=True)


def run_cryodrgn(dataset_name, gpu="0"):
    """Ejecuta CryoDRGN para un dataset específico."""
    config = CRYODRGN_CONFIGS[dataset_name]
    result_dir = RESULTS_DIR / dataset_name
    preproc_dir = result_dir / "preprocessed"
    cryodrgn_dir = result_dir / "cryodrgn"
    cryodrgn_dir.mkdir(parents=True, exist_ok=True)

    log(f"\n{'='*60}")
    log(f"CRYODRGN: {config['description']}")
    log(f"{'='*60}")

    # Verificar preprocesamiento
    meta_file = preproc_dir / "preprocess_meta.json"
    if not meta_file.exists():
        log(f"ERROR: Ejecuta primero scripts/02_preprocess.py")
        return False

    # Verificar si ya se completó
    latent_output = cryodrgn_dir / "latent_space.txt"
    if latent_output.exists():
        log(f"CryoDRGN ya completado para {dataset_name}. Saltando.")
        return True

    # Buscar archivos de entrada
    particles_mrcs = list(preproc_dir.glob("particles_*.mrcs"))
    if not particles_mrcs:
        log(f"ERROR: No se encontraron partículas en {preproc_dir}")
        return False
    particles_mrcs = str(particles_mrcs[0])

    poses_pkl = preproc_dir / "poses.pkl"
    ctf_pkl = preproc_dir / "ctf.pkl"

    if not poses_pkl.exists():
        log(f"ERROR: No se encontró {poses_pkl}")
        return False

    # --- ENTRENAR CRYODRGN ---
    log(f"  Entrenando CryoDRGN (zdim={config['zdim']}, epochs={config['epochs']})...")

    train_cmd = [
        "cryodrgn", "train_vae",
        particles_mrcs,
        "-o", str(cryodrgn_dir),
        "--zdim", str(config["zdim"]),
        "--poses", str(poses_pkl),
        "-n", str(config["epochs"]),
        "-b", str(config["batch_size"]),
        "--lr", str(config["lr"]),
        "--enc-layers", str(config["enc_layers"]),
        "--enc-dim", str(config["enc_dim"]),
        "--dec-layers", str(config["dec_layers"]),
        "--dec-dim", str(config["dec_dim"]),
        "--encode-mode", config["encode_mode"],
    ]

    # CTF si existe
    if ctf_pkl.exists():
        train_cmd.extend(["--ctf", str(ctf_pkl)])

    # Multi-GPU
    if "," in gpu:
        train_cmd.append("--multigpu")

    # Lazy loading para datasets grandes
    with open(meta_file) as f:
        meta = json.load(f)
    if meta.get("n_mrcs_files", 0) > 1 or os.path.getsize(particles_mrcs) > 5e9:
        train_cmd.append("--lazy")

    # Set CUDA device
    env = os.environ.copy()
    env["CUDA_VISIBLE_DEVICES"] = gpu

    log(f"  Comando: cryodrgn train_vae ... --zdim {config['zdim']} -n {config['epochs']}")
    result = subprocess.run(train_cmd, capture_output=True, text=True, env=env)

    if result.returncode != 0:
        log(f"  ERROR en entrenamiento:")
        log(f"  {result.stderr[-500:]}")
        with open(cryodrgn_dir / "train_error.log", "w") as f:
            f.write(result.stdout + "\n" + result.stderr)
        return False

    log("  Entrenamiento completado!")

    # --- EJECUTAR ANÁLISIS ---
    log("  Ejecutando análisis (PCA, K-means, UMAP)...")
    last_epoch = config["epochs"] - 1  # 0-indexed
    analyze_cmd = [
        "cryodrgn", "analyze",
        str(cryodrgn_dir),
        str(last_epoch),
        "--ksample", "20",
    ]

    result = subprocess.run(analyze_cmd, capture_output=True, text=True, env=env)
    if result.returncode != 0:
        log(f"  WARNING: Análisis falló (no crítico): {result.stderr[-200:]}")

    # --- EXTRAER ESPACIO LATENTE ---
    log("  Extrayendo espacio latente...")

    # CryoDRGN guarda z.pkl con z_mu y z_logvar
    z_pkl = cryodrgn_dir / f"z.{last_epoch}.pkl"
    if not z_pkl.exists():
        z_pkl = cryodrgn_dir / "z.pkl"

    if z_pkl.exists():
        with open(z_pkl, "rb") as f:
            z_mu = pickle.load(f)       # (N, zdim) - Media del espacio latente
            z_logvar = pickle.load(f)    # (N, zdim) - Log-varianza

        # Usar z_mu como representación del espacio latente
        np.savetxt(latent_output, z_mu, fmt="%.8f")
        log(f"  Espacio latente guardado: {latent_output} (shape: {z_mu.shape})")

        # También guardar como .npy para uso rápido
        np.save(cryodrgn_dir / "z_mu.npy", z_mu)
        np.save(cryodrgn_dir / "z_logvar.npy", z_logvar)
    else:
        log(f"  ERROR: No se encontró {z_pkl}")
        return False

    # Guardar metadatos del run
    run_meta = {
        "method": "CryoDRGN",
        "dataset": dataset_name,
        "config": config,
        "latent_shape": list(z_mu.shape),
        "z_pkl": str(z_pkl),
    }
    with open(cryodrgn_dir / "run_meta.json", "w") as f:
        json.dump(run_meta, f, indent=2)

    log(f"  CryoDRGN completado para {dataset_name}!")
    return True


# -----------------------------------------------
# Main
# -----------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="FASE 2b: Ejecutar CryoDRGN")
    parser.add_argument("--dataset", required=True,
                        choices=ALL_DATASETS + ["all"],
                        help="Dataset a procesar")
    parser.add_argument("--gpu", default="0", help="GPU IDs (default: 0)")
    args = parser.parse_args()

    datasets = ALL_DATASETS if args.dataset == "all" else [args.dataset]

    results = {}
    for ds in datasets:
        ok = run_cryodrgn(ds, args.gpu)
        results[ds] = "OK" if ok else "FAILED"

    log("\n=== RESUMEN CRYODRGN ===")
    for name, status in results.items():
        log(f"  {name}: {status}")

    log("\nSiguiente paso: python scripts/05_run_flexconsensus.py --dataset ...")


if __name__ == "__main__":
    main()
