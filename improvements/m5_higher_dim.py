#!/usr/bin/env python3
"""
Mejora M5: Consensus space en dimensión > 3
=============================================
Explora si usar 4-5 dimensiones latentes en el consensus space
captura más información conformacional que las 3 dimensiones del paper.

Evaluación:
  - Reconstrucción error (menor = mejor representación)
  - Silhouette score (mayor = mejor separación de clusters)
  - Mantel test con cada espacio individual
  - Variance explicada

Uso:
  python improvements/m5_higher_dim.py --dataset IgG-RL --dims 2,3,4,5,6,8,10 --gpu 0
"""

import argparse
import os
import sys
import json
import subprocess
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent
RESULTS_DIR = PROJECT_DIR / "results"
TOOLKIT_DIR = PROJECT_DIR / "SOFTWARE" / "Flexutils-Toolkit"
ALL_DATASETS = ["IgG-RL", "MDSpike", "Ribosome-80S", "Spike-SARS2"]


def log(msg):
    print(f"[HIGHER-DIM] {msg}", flush=True)


def train_flexconsensus_dim(dataset_name, latent_dim, gpu="0"):
    """Entrena FlexConsensus con una dimensión latente específica."""
    result_dir = RESULTS_DIR / dataset_name
    fc_base = result_dir / "flexconsensus"
    dim_dir = fc_base / f"dim_{latent_dim}"
    dim_dir.mkdir(parents=True, exist_ok=True)

    input_dir = fc_base / "input_spaces"
    if not input_dir.exists():
        log(f"  ERROR: No hay input_spaces. Ejecuta scripts/05_run_flexconsensus.py primero.")
        return None

    # Verificar si ya existe
    consensus_file = dim_dir / "consensus_latents.npy"
    if consensus_file.exists():
        log(f"  dim={latent_dim}: ya existe, cargando...")
        return dim_dir

    log(f"  Entrenando FlexConsensus con dim={latent_dim}...")

    train_script = TOOLKIT_DIR / "tensorflow_toolkit" / "scripts" / "train_flex_consensus.py"
    predict_script = TOOLKIT_DIR / "tensorflow_toolkit" / "scripts" / "predict_flex_consensus.py"

    env = os.environ.copy()
    env["CUDA_VISIBLE_DEVICES"] = gpu

    # Entrenar
    train_args = [
        sys.executable, str(train_script),
        "--data_path", str(input_dir),
        "--out_path", str(dim_dir),
        "--lat_dim", str(latent_dim),
        "--batch_size", "1024",
        "--shuffle",
        "--split_train", "0.8",
        "--lr", "1e-5",
        "--epochs", "100",
        "--gpu", gpu,
    ]

    result = subprocess.run(train_args, capture_output=True, text=True, env=env)
    if result.returncode != 0:
        log(f"  ERROR entrenando dim={latent_dim}: {result.stderr[-200:]}")
        return None

    # Predecir
    weights_file = list(dim_dir.glob("network/flex_consensus_model*"))
    if not weights_file:
        weights_file = list(dim_dir.glob("network/*.h5"))
    if not weights_file:
        return None

    predict_args = [
        sys.executable, str(predict_script),
        "--data_path", str(input_dir),
        "--out_path", str(dim_dir),
        "--weigths_file", str(weights_file[0]),
        "--lat_dim", str(latent_dim),
        "--gpu", gpu,
    ]

    result = subprocess.run(predict_args, capture_output=True, text=True, env=env)
    if result.returncode != 0:
        log(f"  ERROR prediciendo dim={latent_dim}")
        return None

    return dim_dir


def evaluate_dimension(dim_dir, latent_dim, input_dir):
    """Evalúa la calidad de un consensus space de dimensión dada."""
    consensus = np.load(dim_dir / "consensus_latents.npy")
    errors = np.load(dim_dir / "consensus_error.npy")
    rep_errors = np.load(dim_dir / "representation_error.npy") if (dim_dir / "representation_error.npy").exists() else None

    metrics = {
        "latent_dim": latent_dim,
        "n_particles": len(consensus),
        "consensus_error_mean": float(errors.mean()),
        "consensus_error_std": float(errors.std()),
        "consensus_error_median": float(np.median(errors)),
    }

    if rep_errors is not None:
        metrics["representation_error_mean"] = float(rep_errors.mean())

    # Clustering y silhouette score
    try:
        from sklearn.cluster import KMeans
        from sklearn.metrics import silhouette_score

        best_sil = -1
        best_k = 2
        for k in range(2, 8):
            km = KMeans(n_clusters=k, random_state=42, n_init=10)
            labels = km.fit_predict(consensus)
            sil = silhouette_score(consensus, labels, sample_size=min(5000, len(consensus)))
            if sil > best_sil:
                best_sil = sil
                best_k = k

        metrics["best_k"] = best_k
        metrics["silhouette_score"] = float(best_sil)
    except ImportError:
        pass

    # Mantel test con espacios originales
    try:
        from scipy.spatial.distance import pdist
        from scipy.stats import pearsonr

        space_files = sorted(input_dir.glob("*.txt"))
        for sf in space_files:
            space_data = np.loadtxt(sf)
            n = min(3000, len(space_data))
            idx = np.random.choice(len(space_data), n, replace=False)
            d_consensus = pdist(consensus[idx])
            d_space = pdist(space_data[idx])
            r, _ = pearsonr(d_consensus, d_space)
            metrics[f"mantel_{sf.stem}"] = float(r)
    except Exception:
        pass

    # Varianza explicada (ratio de varianza total)
    total_var = np.var(consensus, axis=0).sum()
    metrics["total_variance"] = float(total_var)

    return metrics


def run_dimension_study(dataset_name, dims, gpu="0"):
    """Ejecuta el estudio completo de dimensionalidad."""
    result_dir = RESULTS_DIR / dataset_name
    fig_dir = result_dir / "figures"
    fig_dir.mkdir(parents=True, exist_ok=True)

    log(f"\n{'='*60}")
    log(f"ESTUDIO DE DIMENSIONALIDAD: {dataset_name}")
    log(f"Dimensiones a probar: {dims}")
    log(f"{'='*60}")

    input_dir = result_dir / "flexconsensus" / "input_spaces"
    all_metrics = []

    for dim in dims:
        log(f"\n--- Dimensión {dim} ---")
        dim_dir = train_flexconsensus_dim(dataset_name, dim, gpu)
        if dim_dir:
            metrics = evaluate_dimension(dim_dir, dim, input_dir)
            all_metrics.append(metrics)
            log(f"  Error consenso: {metrics['consensus_error_mean']:.4f}")
            log(f"  Silhouette: {metrics.get('silhouette_score', 'N/A')}")
        else:
            log(f"  Falló para dim={dim}")

    if not all_metrics:
        log("ERROR: No se pudo evaluar ninguna dimensión")
        return

    # Generar figura comparativa
    fig, axes = plt.subplots(2, 2, figsize=(14, 10))

    dims_tested = [m["latent_dim"] for m in all_metrics]

    # 1. Consensus error
    ax = axes[0, 0]
    ax.plot(dims_tested, [m["consensus_error_mean"] for m in all_metrics], "o-", color="#6366f1", linewidth=2)
    ax.set_xlabel("Dimensión latente")
    ax.set_ylabel("Consensus Error (media)")
    ax.set_title("Error de consenso", fontweight="bold")
    ax.grid(alpha=0.3)

    # 2. Silhouette score
    ax = axes[0, 1]
    sil_scores = [m.get("silhouette_score", 0) for m in all_metrics]
    ax.plot(dims_tested, sil_scores, "o-", color="#22c55e", linewidth=2)
    ax.set_xlabel("Dimensión latente")
    ax.set_ylabel("Silhouette Score")
    ax.set_title("Separación de clusters", fontweight="bold")
    ax.grid(alpha=0.3)

    # 3. Mantel correlations
    ax = axes[1, 0]
    for key in [k for k in all_metrics[0].keys() if k.startswith("mantel_")]:
        vals = [m.get(key, 0) for m in all_metrics]
        label = key.replace("mantel_space_", "")
        ax.plot(dims_tested, vals, "o-", linewidth=2, label=label)
    ax.set_xlabel("Dimensión latente")
    ax.set_ylabel("Mantel r")
    ax.set_title("Correlación con espacios originales", fontweight="bold")
    ax.legend()
    ax.grid(alpha=0.3)

    # 4. Optimal K
    ax = axes[1, 1]
    ax.plot(dims_tested, [m.get("best_k", 0) for m in all_metrics], "o-", color="#f59e0b", linewidth=2)
    ax.set_xlabel("Dimensión latente")
    ax.set_ylabel("K óptimo")
    ax.set_title("Número de conformaciones", fontweight="bold")
    ax.grid(alpha=0.3)

    plt.suptitle(f"Estudio de dimensionalidad — {dataset_name}", fontsize=15, fontweight="bold")
    plt.tight_layout()
    path = fig_dir / f"dimension_study_{dataset_name}.png"
    plt.savefig(path, dpi=300, bbox_inches="tight")
    plt.close()
    log(f"\nFigura: {path}")

    # Guardar reporte
    report = {"dataset": dataset_name, "dimensions": all_metrics}
    report_path = fig_dir / f"dimension_study_report_{dataset_name}.json"
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2)

    # Recomendación
    best_dim = max(all_metrics, key=lambda m: m.get("silhouette_score", 0))
    log(f"\n  === RECOMENDACIÓN ===")
    log(f"  Mejor dimensión: {best_dim['latent_dim']}")
    log(f"  Silhouette: {best_dim.get('silhouette_score', 'N/A')}")
    log(f"  Error consenso: {best_dim['consensus_error_mean']:.4f}")


def main():
    parser = argparse.ArgumentParser(description="M5: Consensus space > 3D")
    parser.add_argument("--dataset", required=True, choices=ALL_DATASETS + ["all"])
    parser.add_argument("--dims", default="2,3,4,5,6,8,10", help="Dimensiones a probar (separadas por coma)")
    parser.add_argument("--gpu", default="0")
    args = parser.parse_args()

    dims = [int(d) for d in args.dims.split(",")]
    datasets = ALL_DATASETS if args.dataset == "all" else [args.dataset]

    for ds in datasets:
        run_dimension_study(ds, dims, args.gpu)


if __name__ == "__main__":
    main()
