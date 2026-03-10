#!/usr/bin/env python3
"""
FlexConsensus - FASE 4: Validación y generación de figuras
===========================================================
Valida los resultados de FlexConsensus y genera las figuras del paper.

Métricas:
  - Test de Mantel: Correlación espacial entre métodos
  - Consensus error distribution
  - Comparación antes/después del filtrado
  - Poblaciones conformacionales vs ground truth (CryoBench)

Figuras replicadas:
  - Fig 1: IgG-RL consensus space
  - Fig 2: MDSpike consensus space
  - Fig 3: Ribosome 80S consensus space
  - Fig 4: SARS-CoV-2 Spike consensus space
  - Fig 5: Spike filtrado (efecto del consensus error)

Uso:
  python scripts/06_validate.py --dataset IgG-RL
  python scripts/06_validate.py --dataset all
"""

import argparse
import os
import json
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import cm
from mpl_toolkits.mplot3d import Axes3D
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent
RESULTS_DIR = PROJECT_DIR / "results"

ALL_DATASETS = ["IgG-RL", "MDSpike", "Ribosome-80S", "Spike-SARS2"]

# Mapeo a figuras del paper
PAPER_FIGURES = {
    "IgG-RL": "Fig. 1",
    "MDSpike": "Fig. 2",
    "Ribosome-80S": "Fig. 3",
    "Spike-SARS2": "Fig. 4-5",
}


def log(msg):
    print(f"[VALIDATE] {msg}", flush=True)


# -----------------------------------------------
# Test de Mantel
# -----------------------------------------------
def mantel_test(X, Y, n_permutations=999, subsample=5000):
    """
    Test de Mantel: mide la correlación entre dos matrices de distancia.
    Si r es alto y p es bajo, los dos métodos detectan patrones similares.

    Args:
        X: array (N, d1) - espacio latente método 1
        Y: array (N, d2) - espacio latente método 2
        n_permutations: número de permutaciones para p-valor
        subsample: submuestrear si N es muy grande

    Returns:
        r: correlación de Mantel (-1 a 1)
        p: p-valor
    """
    from scipy.spatial.distance import pdist, squareform
    from scipy.stats import pearsonr

    N = len(X)
    if N > subsample:
        idx = np.random.choice(N, subsample, replace=False)
        X = X[idx]
        Y = Y[idx]
        N = subsample

    log(f"  Calculando matrices de distancia ({N} muestras)...")

    # Matrices de distancia condensadas
    dX = pdist(X, metric="euclidean")
    dY = pdist(Y, metric="euclidean")

    # Correlación observada
    r_obs, _ = pearsonr(dX, dY)

    # Test de permutación
    log(f"  Ejecutando {n_permutations} permutaciones...")
    r_perms = np.zeros(n_permutations)
    for i in range(n_permutations):
        perm = np.random.permutation(N)
        Y_perm = Y[perm]
        dY_perm = pdist(Y_perm, metric="euclidean")
        r_perms[i], _ = pearsonr(dX, dY_perm)

    # p-valor: proporción de permutaciones con r >= r_obs
    p_value = (np.sum(r_perms >= r_obs) + 1) / (n_permutations + 1)

    return float(r_obs), float(p_value)


# -----------------------------------------------
# Figuras
# -----------------------------------------------
def plot_consensus_space(consensus, labels, errors, dataset_name, fig_dir):
    """
    Genera figura del consensus space (réplica de Figs. 1-4 del paper).
    Panel A: Coloreado por conformación
    Panel B: Coloreado por consensus error
    """
    fig = plt.figure(figsize=(16, 7))

    # Panel A: Por conformación
    ax1 = fig.add_subplot(121, projection="3d")
    scatter1 = ax1.scatter(
        consensus[:, 0], consensus[:, 1], consensus[:, 2],
        c=labels, cmap="tab10", s=1, alpha=0.5,
    )
    ax1.set_xlabel("Dim 1", fontsize=10)
    ax1.set_ylabel("Dim 2", fontsize=10)
    ax1.set_zlabel("Dim 3", fontsize=10)
    ax1.set_title(f"{dataset_name} — Conformaciones", fontsize=13, fontweight="bold")
    plt.colorbar(scatter1, ax=ax1, label="Conformación", shrink=0.6)

    # Panel B: Por consensus error
    ax2 = fig.add_subplot(122, projection="3d")
    scatter2 = ax2.scatter(
        consensus[:, 0], consensus[:, 1], consensus[:, 2],
        c=errors, cmap="viridis", s=1, alpha=0.5,
    )
    ax2.set_xlabel("Dim 1", fontsize=10)
    ax2.set_ylabel("Dim 2", fontsize=10)
    ax2.set_zlabel("Dim 3", fontsize=10)
    ax2.set_title(f"{dataset_name} — Consensus Error", fontsize=13, fontweight="bold")
    plt.colorbar(scatter2, ax=ax2, label="Error", shrink=0.6)

    plt.suptitle(
        f"FlexConsensus — {dataset_name} ({PAPER_FIGURES.get(dataset_name, '')})",
        fontsize=15, fontweight="bold", y=1.02,
    )
    plt.tight_layout()
    path = fig_dir / f"consensus_space_{dataset_name}.png"
    plt.savefig(path, dpi=300, bbox_inches="tight")
    plt.close()
    log(f"  Figura guardada: {path.name}")
    return path


def plot_error_histogram(errors, dataset_name, fig_dir):
    """Genera histograma de consensus error con umbrales P20/P80."""
    fig, ax = plt.subplots(figsize=(10, 6))

    p20 = np.percentile(errors, 20)
    p80 = np.percentile(errors, 80)

    # Histograma coloreado
    counts, bins, patches = ax.hist(errors, bins=80, alpha=0.8, edgecolor="white", linewidth=0.3)
    for patch, left_edge in zip(patches, bins[:-1]):
        if left_edge < p20:
            patch.set_facecolor("#22c55e")
        elif left_edge < p80:
            patch.set_facecolor("#6366f1")
        else:
            patch.set_facecolor("#ef4444")

    # Líneas de umbral
    ax.axvline(p20, color="#22c55e", linestyle="--", linewidth=2, label=f"P20 = {p20:.4f} (Fiable)")
    ax.axvline(p80, color="#ef4444", linestyle="--", linewidth=2, label=f"P80 = {p80:.4f} (No fiable)")
    ax.axvline(np.median(errors), color="orange", linestyle=":", linewidth=1.5,
               label=f"Mediana = {np.median(errors):.4f}")

    ax.set_xlabel("Consensus Error", fontsize=12)
    ax.set_ylabel("Número de partículas", fontsize=12)
    ax.set_title(f"Distribución de Consensus Error — {dataset_name}", fontsize=14, fontweight="bold")
    ax.legend(fontsize=10)
    ax.grid(axis="y", alpha=0.3)

    path = fig_dir / f"error_histogram_{dataset_name}.png"
    plt.savefig(path, dpi=300, bbox_inches="tight")
    plt.close()
    log(f"  Figura guardada: {path.name}")
    return path


def plot_filtering_comparison(consensus, labels, errors, dataset_name, fig_dir):
    """
    Compara antes/después del filtrado (réplica de Fig. 5 del paper).
    Solo las partículas con bajo consensus error (P20) se mantienen.
    """
    p20_threshold = np.percentile(errors, 20)
    reliable_mask = errors < p20_threshold

    fig, axes = plt.subplots(1, 2, figsize=(16, 7))

    # Antes: todas las partículas en gris
    axes[0].scatter(
        consensus[:, 0], consensus[:, 1],
        c="gray", s=1, alpha=0.2,
    )
    axes[0].set_title(f"Todas las partículas ({len(consensus):,})", fontsize=13, fontweight="bold")
    axes[0].set_xlabel("Dim 1")
    axes[0].set_ylabel("Dim 2")

    # Después: solo fiables, coloreadas
    scatter = axes[1].scatter(
        consensus[reliable_mask, 0], consensus[reliable_mask, 1],
        c=labels[reliable_mask], cmap="tab10", s=3, alpha=0.7,
    )
    n_reliable = reliable_mask.sum()
    axes[1].set_title(
        f"Partículas fiables ({n_reliable:,} / {len(consensus):,} = {100*n_reliable/len(consensus):.1f}%)",
        fontsize=13, fontweight="bold",
    )
    axes[1].set_xlabel("Dim 1")
    axes[1].set_ylabel("Dim 2")
    plt.colorbar(scatter, ax=axes[1], label="Conformación")

    plt.suptitle(
        f"Efecto del filtrado por Consensus Error — {dataset_name}",
        fontsize=15, fontweight="bold",
    )
    plt.tight_layout()
    path = fig_dir / f"filtering_{dataset_name}.png"
    plt.savefig(path, dpi=300, bbox_inches="tight")
    plt.close()
    log(f"  Figura guardada: {path.name}")
    return path


def plot_individual_spaces(dataset_name, fig_dir):
    """Genera visualización de espacios individuales (HetSIREN vs CryoDRGN)."""
    result_dir = RESULTS_DIR / dataset_name

    spaces = {}
    for method in ["hetsiren", "cryodrgn"]:
        latent_file = result_dir / method / "latent_space.txt"
        if latent_file.exists():
            spaces[method] = np.loadtxt(latent_file)

    if len(spaces) < 2:
        log("  WARNING: No hay 2 espacios para comparar")
        return None

    # Reducir a 3D si es necesario
    from sklearn.decomposition import PCA
    fig = plt.figure(figsize=(16, 7))

    for idx, (method, data) in enumerate(spaces.items()):
        if data.shape[1] > 3:
            pca = PCA(n_components=3)
            data_3d = pca.fit_transform(data)
        else:
            data_3d = data[:, :3]

        ax = fig.add_subplot(1, 2, idx + 1, projection="3d")
        ax.scatter(data_3d[:, 0], data_3d[:, 1], data_3d[:, 2], s=1, alpha=0.3, c="#6366f1")
        ax.set_xlabel("Dim 1")
        ax.set_ylabel("Dim 2")
        ax.set_zlabel("Dim 3")
        name = "CryoDRGN" if method == "cryodrgn" else "HetSIREN"
        ax.set_title(f"{name} (dim={spaces[method].shape[1]})", fontsize=13, fontweight="bold")

    plt.suptitle(f"Espacios latentes individuales — {dataset_name}", fontsize=15, fontweight="bold")
    plt.tight_layout()
    path = fig_dir / f"individual_spaces_{dataset_name}.png"
    plt.savefig(path, dpi=300, bbox_inches="tight")
    plt.close()
    log(f"  Figura guardada: {path.name}")
    return path


# -----------------------------------------------
# Validación con Ground Truth (CryoBench)
# -----------------------------------------------
def validate_against_ground_truth(dataset_name, labels, consensus):
    """
    Para datasets CryoBench que tienen ground truth,
    compara las conformaciones detectadas con las reales.
    """
    preproc_dir = RESULTS_DIR / dataset_name / "preprocessed"

    import glob
    gt_files = glob.glob(str(preproc_dir / "*ground_truth*"))
    gt_files += glob.glob(str(preproc_dir / "*gt*"))
    gt_files += glob.glob(str(preproc_dir / "*labels*"))
    gt_files += glob.glob(str(preproc_dir / "*conformations*"))

    if not gt_files:
        log("  No hay ground truth para este dataset")
        return None

    log("  Comparando con ground truth...")
    for gt_file in gt_files:
        try:
            gt = np.load(gt_file) if gt_file.endswith(".npy") else np.loadtxt(gt_file)
            if len(gt) == len(labels):
                # Calcular Adjusted Rand Index
                from sklearn.metrics import adjusted_rand_score, normalized_mutual_info_score
                ari = adjusted_rand_score(gt, labels)
                nmi = normalized_mutual_info_score(gt, labels)
                log(f"  Ground truth: {Path(gt_file).name}")
                log(f"    ARI (Adjusted Rand Index): {ari:.4f}")
                log(f"    NMI (Normalized Mutual Info): {nmi:.4f}")
                return {"ari": ari, "nmi": nmi, "gt_file": str(gt_file)}
        except Exception as e:
            log(f"  Warning al leer {gt_file}: {e}")

    return None


# -----------------------------------------------
# Main: Validar dataset
# -----------------------------------------------
def validate_dataset(dataset_name):
    """Ejecuta toda la validación para un dataset."""
    result_dir = RESULTS_DIR / dataset_name
    fc_dir = result_dir / "flexconsensus"
    fig_dir = result_dir / "figures"
    fig_dir.mkdir(parents=True, exist_ok=True)

    log(f"\n{'='*60}")
    log(f"VALIDACIÓN: {dataset_name} ({PAPER_FIGURES.get(dataset_name, '')})")
    log(f"{'='*60}")

    # Cargar resultados de FlexConsensus
    consensus_file = fc_dir / "consensus_latents.npy"
    errors_file = fc_dir / "consensus_error.npy"
    labels_file = fc_dir / "cluster_labels.npy"

    if not consensus_file.exists():
        log(f"ERROR: No se encontró {consensus_file}")
        log(f"Ejecuta primero: python scripts/05_run_flexconsensus.py --dataset {dataset_name}")
        return False

    consensus = np.load(consensus_file)
    errors = np.load(errors_file) if errors_file.exists() else np.zeros(len(consensus))
    labels = np.load(labels_file) if labels_file.exists() else np.zeros(len(consensus), dtype=int)

    n_particles = len(consensus)
    n_conformations = len(np.unique(labels))
    log(f"  Partículas: {n_particles:,}")
    log(f"  Conformaciones: {n_conformations}")
    log(f"  Consensus error: media={errors.mean():.4f}, std={errors.std():.4f}")

    # -----------------------------------------------
    # 1. Test de Mantel
    # -----------------------------------------------
    log("\n  --- Test de Mantel ---")
    hetsiren_latent = result_dir / "hetsiren" / "latent_space.txt"
    cryodrgn_latent = result_dir / "cryodrgn" / "latent_space.txt"

    mantel_result = None
    if hetsiren_latent.exists() and cryodrgn_latent.exists():
        X = np.loadtxt(hetsiren_latent)
        Y = np.loadtxt(cryodrgn_latent)
        r, p = mantel_test(X, Y)
        log(f"  Mantel r = {r:.4f}, p = {p:.6f}")
        log(f"  Interpretación: {'ALTA' if r > 0.7 else 'MODERADA' if r > 0.5 else 'BAJA'} concordancia")
        mantel_result = {"r": r, "p": p}
    else:
        log("  WARNING: No se pueden cargar ambos espacios para Mantel")

    # -----------------------------------------------
    # 2. Métricas de fiabilidad
    # -----------------------------------------------
    log("\n  --- Métricas de fiabilidad ---")
    p20 = np.percentile(errors, 20)
    p80 = np.percentile(errors, 80)
    reliable_mask = errors < p20
    n_reliable = reliable_mask.sum()
    pct_reliable = 100 * n_reliable / n_particles

    log(f"  P20 threshold: {p20:.4f}")
    log(f"  P80 threshold: {p80:.4f}")
    log(f"  Partículas fiables (P20): {n_reliable:,} ({pct_reliable:.1f}%)")

    # Por conformación
    log("\n  --- Fiabilidad por conformación ---")
    per_conf = []
    for i in range(n_conformations):
        mask = labels == i
        n = mask.sum()
        pct = 100 * n / n_particles
        err_mean = errors[mask].mean()
        err_std = errors[mask].std()
        reliable_in_conf = (mask & reliable_mask).sum()
        pct_reliable_conf = 100 * reliable_in_conf / n if n > 0 else 0

        per_conf.append({
            "conformation": i,
            "n_particles": int(n),
            "percentage": round(pct, 1),
            "error_mean": round(float(err_mean), 4),
            "error_std": round(float(err_std), 4),
            "reliable_pct": round(pct_reliable_conf, 1),
        })
        log(f"  Conf {i}: {n:,} ({pct:.1f}%), error={err_mean:.4f}±{err_std:.4f}, "
            f"fiable={pct_reliable_conf:.1f}%")

    # -----------------------------------------------
    # 3. Ground Truth (si CryoBench)
    # -----------------------------------------------
    gt_result = validate_against_ground_truth(dataset_name, labels, consensus)

    # -----------------------------------------------
    # 4. Generar figuras
    # -----------------------------------------------
    log("\n  --- Generando figuras ---")
    plot_consensus_space(consensus, labels, errors, dataset_name, fig_dir)
    plot_error_histogram(errors, dataset_name, fig_dir)
    plot_filtering_comparison(consensus, labels, errors, dataset_name, fig_dir)
    plot_individual_spaces(dataset_name, fig_dir)

    # -----------------------------------------------
    # 5. Guardar reporte completo
    # -----------------------------------------------
    report = {
        "dataset": dataset_name,
        "paper_figure": PAPER_FIGURES.get(dataset_name),
        "n_particles": n_particles,
        "n_conformations": n_conformations,
        "consensus_error": {
            "mean": round(float(errors.mean()), 4),
            "std": round(float(errors.std()), 4),
            "p20": round(float(p20), 4),
            "p80": round(float(p80), 4),
            "median": round(float(np.median(errors)), 4),
        },
        "reliability": {
            "n_reliable": n_reliable,
            "pct_reliable": round(pct_reliable, 1),
        },
        "mantel_test": mantel_result,
        "per_conformation": per_conf,
        "ground_truth": gt_result,
        "figures": [str(p) for p in fig_dir.glob("*.png")],
    }

    report_path = fig_dir / f"validation_report_{dataset_name}.json"
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2)
    log(f"\n  Reporte guardado: {report_path}")

    # Resumen
    log(f"\n  === RESUMEN {dataset_name} ===")
    log(f"  Partículas: {n_particles:,}")
    log(f"  Conformaciones: {n_conformations}")
    if mantel_result:
        log(f"  Mantel: r={mantel_result['r']:.4f}, p={mantel_result['p']:.6f}")
    log(f"  Fiables: {n_reliable:,} ({pct_reliable:.1f}%)")
    if gt_result:
        log(f"  ARI vs GT: {gt_result['ari']:.4f}")
    log(f"  Figuras: {len(list(fig_dir.glob('*.png')))}")

    return True


# -----------------------------------------------
# Main
# -----------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="FASE 4: Validación y figuras")
    parser.add_argument("--dataset", required=True,
                        choices=ALL_DATASETS + ["all"],
                        help="Dataset a validar")
    args = parser.parse_args()

    datasets = ALL_DATASETS if args.dataset == "all" else [args.dataset]

    results = {}
    for ds in datasets:
        ok = validate_dataset(ds)
        results[ds] = "OK" if ok else "FAILED"

    log("\n=== RESUMEN VALIDACIÓN ===")
    for name, status in results.items():
        log(f"  {name}: {status}")

    log("\nFiguras en: results/<dataset>/figures/")
    log("Reportes en: results/<dataset>/figures/validation_report_*.json")


if __name__ == "__main__":
    main()
