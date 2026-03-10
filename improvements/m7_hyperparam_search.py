#!/usr/bin/env python3
"""
Mejora M7: Optimización de hiperparámetros
============================================
Grid search sobre los hiperparámetros del multi-autoencoder FlexConsensus.

Parámetros a optimizar:
  - Learning rate: [1e-6, 5e-6, 1e-5, 5e-5, 1e-4]
  - Batch size: [256, 512, 1024, 2048]
  - Latent dim: [2, 3, 4, 5]
  - Split train: [0.7, 0.8, 0.9, 1.0]

Métrica objetivo: Minimizar consensus error + maximizar silhouette score

Uso:
  python improvements/m7_hyperparam_search.py --dataset IgG-RL --gpu 0
  python improvements/m7_hyperparam_search.py --dataset IgG-RL --mode random --n-trials 20
"""

import argparse
import os
import sys
import json
import subprocess
import time
import itertools
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent
RESULTS_DIR = PROJECT_DIR / "results"
TOOLKIT_DIR = PROJECT_DIR / "SOFTWARE" / "Flexutils-Toolkit"
ALL_DATASETS = ["IgG-RL", "MDSpike", "Ribosome-80S", "Spike-SARS2"]

# Espacio de hiperparámetros
PARAM_GRID = {
    "lr": [1e-6, 5e-6, 1e-5, 5e-5, 1e-4],
    "batch_size": [256, 512, 1024, 2048],
    "latent_dim": [2, 3, 4, 5],
    "split_train": [0.7, 0.8, 0.9, 1.0],
}

# Grid reducido para modo rápido
PARAM_GRID_QUICK = {
    "lr": [1e-5, 5e-5, 1e-4],
    "batch_size": [512, 1024],
    "latent_dim": [3],
    "split_train": [0.8],
}


def log(msg):
    print(f"[HYPERPARAM] {msg}", flush=True)


def train_and_evaluate(dataset_name, params, trial_id, gpu="0"):
    """Entrena FlexConsensus con parámetros específicos y evalúa."""
    result_dir = RESULTS_DIR / dataset_name
    fc_dir = result_dir / "flexconsensus"
    input_dir = fc_dir / "input_spaces"
    trial_dir = fc_dir / "hyperparam_search" / f"trial_{trial_id:03d}"
    trial_dir.mkdir(parents=True, exist_ok=True)

    if not input_dir.exists():
        return None

    log(f"  Trial {trial_id}: lr={params['lr']}, bs={params['batch_size']}, "
        f"dim={params['latent_dim']}, split={params['split_train']}")

    # Verificar si ya existe
    result_file = trial_dir / "trial_result.json"
    if result_file.exists():
        with open(result_file) as f:
            return json.load(f)

    env = os.environ.copy()
    env["CUDA_VISIBLE_DEVICES"] = gpu

    train_script = TOOLKIT_DIR / "tensorflow_toolkit" / "scripts" / "train_flex_consensus.py"
    predict_script = TOOLKIT_DIR / "tensorflow_toolkit" / "scripts" / "predict_flex_consensus.py"

    # Entrenar (épocas reducidas para la búsqueda)
    epochs = 50  # Reducido de 100 para busqueda
    start_time = time.time()

    train_args = [
        sys.executable, str(train_script),
        "--data_path", str(input_dir),
        "--out_path", str(trial_dir),
        "--lat_dim", str(params["latent_dim"]),
        "--batch_size", str(params["batch_size"]),
        "--shuffle",
        "--split_train", str(params["split_train"]),
        "--lr", str(params["lr"]),
        "--epochs", str(epochs),
        "--gpu", gpu,
    ]

    result = subprocess.run(train_args, capture_output=True, text=True, env=env, timeout=600)
    train_time = time.time() - start_time

    if result.returncode != 0:
        log(f"    Trial {trial_id}: FALLÓ ({result.stderr[-100:]})")
        trial_result = {"trial_id": trial_id, "params": params, "status": "failed",
                        "error": result.stderr[-200:]}
        with open(result_file, "w") as f:
            json.dump(trial_result, f, indent=2)
        return trial_result

    # Predecir
    weights_files = list(trial_dir.glob("network/flex_consensus_model*"))
    if not weights_files:
        weights_files = list(trial_dir.glob("network/*.h5"))
    if not weights_files:
        return {"trial_id": trial_id, "params": params, "status": "no_weights"}

    predict_args = [
        sys.executable, str(predict_script),
        "--data_path", str(input_dir),
        "--out_path", str(trial_dir),
        "--weigths_file", str(weights_files[0]),
        "--lat_dim", str(params["latent_dim"]),
        "--gpu", gpu,
    ]

    result = subprocess.run(predict_args, capture_output=True, text=True, env=env, timeout=300)
    if result.returncode != 0:
        return {"trial_id": trial_id, "params": params, "status": "predict_failed"}

    # Evaluar
    consensus_file = trial_dir / "consensus_latents.npy"
    errors_file = trial_dir / "consensus_error.npy"

    if not consensus_file.exists():
        return {"trial_id": trial_id, "params": params, "status": "no_output"}

    consensus = np.load(consensus_file)
    errors = np.load(errors_file)

    metrics = {
        "consensus_error_mean": float(errors.mean()),
        "consensus_error_std": float(errors.std()),
        "consensus_error_median": float(np.median(errors)),
    }

    # Silhouette score
    try:
        from sklearn.cluster import KMeans
        from sklearn.metrics import silhouette_score

        best_sil = -1
        for k in range(2, 6):
            km = KMeans(n_clusters=k, random_state=42, n_init=10)
            labels = km.fit_predict(consensus)
            sil = silhouette_score(consensus, labels, sample_size=min(5000, len(consensus)))
            if sil > best_sil:
                best_sil = sil
        metrics["silhouette_score"] = float(best_sil)
    except Exception:
        metrics["silhouette_score"] = 0

    # Score compuesto: minimizar error + maximizar silhouette
    metrics["composite_score"] = float(metrics["silhouette_score"] - metrics["consensus_error_mean"])

    trial_result = {
        "trial_id": trial_id,
        "params": params,
        "status": "completed",
        "metrics": metrics,
        "train_time_s": round(train_time, 1),
    }

    with open(result_file, "w") as f:
        json.dump(trial_result, f, indent=2)

    log(f"    Trial {trial_id}: error={metrics['consensus_error_mean']:.4f}, "
        f"sil={metrics['silhouette_score']:.4f}, score={metrics['composite_score']:.4f} "
        f"({train_time:.0f}s)")

    return trial_result


def run_grid_search(dataset_name, gpu="0", quick=False):
    """Ejecuta grid search completo."""
    grid = PARAM_GRID_QUICK if quick else PARAM_GRID
    log(f"\n{'='*60}")
    log(f"GRID SEARCH: {dataset_name}")
    log(f"{'='*60}")

    # Generar todas las combinaciones
    keys = list(grid.keys())
    values = list(grid.values())
    combinations = list(itertools.product(*values))
    n_trials = len(combinations)
    log(f"  Total combinaciones: {n_trials}")

    all_results = []
    for i, combo in enumerate(combinations):
        params = dict(zip(keys, combo))
        result = train_and_evaluate(dataset_name, params, i, gpu)
        if result:
            all_results.append(result)

    return all_results


def run_random_search(dataset_name, n_trials=20, gpu="0"):
    """Ejecuta random search para explorar el espacio más eficientemente."""
    log(f"\n{'='*60}")
    log(f"RANDOM SEARCH: {dataset_name} ({n_trials} trials)")
    log(f"{'='*60}")

    all_results = []
    for i in range(n_trials):
        params = {
            "lr": float(10 ** np.random.uniform(-6, -3)),
            "batch_size": int(np.random.choice([128, 256, 512, 1024, 2048])),
            "latent_dim": int(np.random.choice([2, 3, 4, 5, 6, 8])),
            "split_train": float(np.random.choice([0.7, 0.8, 0.9, 1.0])),
        }
        result = train_and_evaluate(dataset_name, params, i, gpu)
        if result:
            all_results.append(result)

    return all_results


def analyze_results(all_results, dataset_name):
    """Analiza y visualiza los resultados de la búsqueda."""
    fig_dir = RESULTS_DIR / dataset_name / "figures"
    fig_dir.mkdir(parents=True, exist_ok=True)

    completed = [r for r in all_results if r.get("status") == "completed"]
    if not completed:
        log("  No hay resultados completados para analizar")
        return

    log(f"\n  {len(completed)}/{len(all_results)} trials completados")

    # Mejor trial
    best = max(completed, key=lambda r: r["metrics"]["composite_score"])
    log(f"\n  === MEJOR CONFIGURACIÓN ===")
    log(f"  Trial: {best['trial_id']}")
    log(f"  Parámetros: {best['params']}")
    log(f"  Consensus Error: {best['metrics']['consensus_error_mean']:.4f}")
    log(f"  Silhouette: {best['metrics']['silhouette_score']:.4f}")
    log(f"  Score compuesto: {best['metrics']['composite_score']:.4f}")

    # Comparar con default (lr=1e-5, bs=1024, dim=3, split=0.8)
    default_trials = [r for r in completed
                      if abs(r["params"]["lr"] - 1e-5) < 1e-7
                      and r["params"]["batch_size"] == 1024
                      and r["params"]["latent_dim"] == 3]
    if default_trials:
        default = default_trials[0]
        improvement = best["metrics"]["composite_score"] - default["metrics"]["composite_score"]
        log(f"\n  Mejora vs default: {improvement:+.4f}")

    # Generar figura
    fig, axes = plt.subplots(2, 2, figsize=(14, 10))

    # Extraer parámetros
    lrs = [r["params"]["lr"] for r in completed]
    batch_sizes = [r["params"]["batch_size"] for r in completed]
    scores = [r["metrics"]["composite_score"] for r in completed]
    errors = [r["metrics"]["consensus_error_mean"] for r in completed]

    # 1. Score vs Learning Rate
    ax = axes[0, 0]
    ax.scatter(lrs, scores, c=scores, cmap="RdYlGn", s=80, alpha=0.7, edgecolors="white")
    ax.set_xscale("log")
    ax.set_xlabel("Learning Rate")
    ax.set_ylabel("Score Compuesto")
    ax.set_title("Score vs Learning Rate", fontweight="bold")
    ax.grid(alpha=0.3)

    # 2. Score vs Batch Size
    ax = axes[0, 1]
    ax.scatter(batch_sizes, scores, c=scores, cmap="RdYlGn", s=80, alpha=0.7, edgecolors="white")
    ax.set_xlabel("Batch Size")
    ax.set_ylabel("Score Compuesto")
    ax.set_title("Score vs Batch Size", fontweight="bold")
    ax.grid(alpha=0.3)

    # 3. Error vs Silhouette (Pareto front)
    ax = axes[1, 0]
    sils = [r["metrics"]["silhouette_score"] for r in completed]
    scatter = ax.scatter(errors, sils, c=scores, cmap="RdYlGn", s=80, alpha=0.7, edgecolors="white")
    ax.scatter([best["metrics"]["consensus_error_mean"]], [best["metrics"]["silhouette_score"]],
               c="red", s=200, marker="*", zorder=5, label="Best")
    ax.set_xlabel("Consensus Error")
    ax.set_ylabel("Silhouette Score")
    ax.set_title("Pareto Front: Error vs Silhouette", fontweight="bold")
    ax.legend()
    ax.grid(alpha=0.3)
    plt.colorbar(scatter, ax=ax, label="Score")

    # 4. Top 10 configuraciones
    ax = axes[1, 1]
    top10 = sorted(completed, key=lambda r: r["metrics"]["composite_score"], reverse=True)[:10]
    labels = [f"lr={r['params']['lr']:.0e}\nbs={r['params']['batch_size']}" for r in top10]
    values = [r["metrics"]["composite_score"] for r in top10]
    colors = plt.cm.RdYlGn(np.linspace(0.9, 0.3, 10))
    ax.barh(range(10), values, color=colors)
    ax.set_yticks(range(10))
    ax.set_yticklabels(labels, fontsize=8)
    ax.set_xlabel("Score Compuesto")
    ax.set_title("Top 10 Configuraciones", fontweight="bold")
    ax.invert_yaxis()

    plt.suptitle(f"Búsqueda de Hiperparámetros — {dataset_name}", fontsize=15, fontweight="bold")
    plt.tight_layout()
    path = fig_dir / f"hyperparam_search_{dataset_name}.png"
    plt.savefig(path, dpi=300, bbox_inches="tight")
    plt.close()
    log(f"\n  Figura: {path}")

    # Guardar reporte
    report = {
        "dataset": dataset_name,
        "n_trials": len(all_results),
        "n_completed": len(completed),
        "best_params": best["params"],
        "best_metrics": best["metrics"],
        "all_results": all_results,
    }
    report_path = fig_dir / f"hyperparam_report_{dataset_name}.json"
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2, default=str)


def main():
    parser = argparse.ArgumentParser(description="M7: Optimización de hiperparámetros")
    parser.add_argument("--dataset", required=True, choices=ALL_DATASETS + ["all"])
    parser.add_argument("--mode", default="grid", choices=["grid", "random", "quick"])
    parser.add_argument("--n-trials", type=int, default=20, help="Trials para random search")
    parser.add_argument("--gpu", default="0")
    args = parser.parse_args()

    datasets = ALL_DATASETS if args.dataset == "all" else [args.dataset]

    for ds in datasets:
        if args.mode == "grid":
            results = run_grid_search(ds, args.gpu)
        elif args.mode == "random":
            results = run_random_search(ds, args.n_trials, args.gpu)
        else:  # quick
            results = run_grid_search(ds, args.gpu, quick=True)

        analyze_results(results, ds)


if __name__ == "__main__":
    main()
