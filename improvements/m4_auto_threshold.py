#!/usr/bin/env python3
"""
Mejora M4: Selección automática de umbral de fiabilidad
========================================================
En el paper original, el umbral P20 se elige manualmente.
Esta mejora implementa selección automática del threshold usando:

1. Permutation test (del paper, pero automatizado)
2. Gaussian Mixture Model para separar fiable/no fiable
3. Knee/elbow detection en la curva de error
4. Otsu's method adaptado a distribución continua

Uso:
  python improvements/m4_auto_threshold.py --dataset IgG-RL
  python improvements/m4_auto_threshold.py --dataset all --method all
"""

import argparse
import json
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent
RESULTS_DIR = PROJECT_DIR / "results"
ALL_DATASETS = ["IgG-RL", "MDSpike", "Ribosome-80S", "Spike-SARS2"]


def log(msg):
    print(f"[AUTO-THRESHOLD] {msg}", flush=True)


# -----------------------------------------------
# Método 1: Permutation Test (paper original, automatizado)
# -----------------------------------------------
def permutation_threshold(errors, labels, n_permutations=1000, alpha=0.05):
    """
    Test de permutación para determinar qué partículas tienen
    consensus error significativamente bajo (no por azar).

    Para cada partícula, se compara su error real con la distribución
    de errores bajo permutaciones aleatorias de las etiquetas.
    """
    log("  [Permutation Test] Calculando...")
    n = len(errors)
    observed_errors = errors.copy()

    # Generar distribución nula por permutación
    null_errors = np.zeros((n_permutations, n))
    for i in range(n_permutations):
        perm = np.random.permutation(n)
        null_errors[i] = errors[perm]

    # p-valor por partícula: proporción de permutaciones con error <= observado
    p_values = np.zeros(n)
    for j in range(n):
        p_values[j] = (np.sum(null_errors[:, j] <= observed_errors[j]) + 1) / (n_permutations + 1)

    # Threshold: partículas con p < alpha son significativamente fiables
    reliable_mask = p_values < alpha
    threshold = np.percentile(errors[reliable_mask], 100) if reliable_mask.any() else np.median(errors)

    n_reliable = reliable_mask.sum()
    log(f"  [Permutation] Threshold: {threshold:.4f}, Fiables: {n_reliable} ({100*n_reliable/n:.1f}%)")
    return threshold, reliable_mask, {"method": "permutation", "alpha": alpha, "p_values_mean": float(p_values.mean())}


# -----------------------------------------------
# Método 2: Gaussian Mixture Model
# -----------------------------------------------
def gmm_threshold(errors):
    """
    Ajusta un GMM de 2 componentes a la distribución de errores.
    La componente con menor media = partículas fiables.
    El threshold es la intersección entre las dos Gaussianas.
    """
    from sklearn.mixture import GaussianMixture

    log("  [GMM] Ajustando 2 componentes...")
    errors_2d = errors.reshape(-1, 1)

    gmm = GaussianMixture(n_components=2, random_state=42, max_iter=200)
    gmm.fit(errors_2d)

    means = gmm.means_.flatten()
    stds = np.sqrt(gmm.covariances_.flatten())
    weights = gmm.weights_

    # Componente fiable = la de menor media
    reliable_idx = np.argmin(means)
    unreliable_idx = 1 - reliable_idx

    # Encontrar intersección analítica
    # Para dos Gaussianas, resolver: w1*N(x|mu1,s1) = w2*N(x|mu2,s2)
    mu1, s1, w1 = means[reliable_idx], stds[reliable_idx], weights[reliable_idx]
    mu2, s2, w2 = means[unreliable_idx], stds[unreliable_idx], weights[unreliable_idx]

    # Buscar intersección numéricamente
    x_range = np.linspace(min(errors), max(errors), 10000)
    from scipy.stats import norm
    pdf1 = w1 * norm.pdf(x_range, mu1, s1)
    pdf2 = w2 * norm.pdf(x_range, mu2, s2)
    diff = pdf1 - pdf2
    # Buscar el cruce donde diff cambia de signo, entre las dos medias
    crossings = np.where(np.diff(np.sign(diff)))[0]
    valid_crossings = crossings[(x_range[crossings] > mu1) & (x_range[crossings] < mu2)]

    if len(valid_crossings) > 0:
        threshold = x_range[valid_crossings[0]]
    else:
        threshold = (mu1 + mu2) / 2

    reliable_mask = errors < threshold
    n_reliable = reliable_mask.sum()
    log(f"  [GMM] Threshold: {threshold:.4f}, Fiables: {n_reliable} ({100*n_reliable/len(errors):.1f}%)")
    log(f"    Componente fiable: mu={mu1:.4f}, std={s1:.4f}, weight={w1:.2f}")
    log(f"    Componente no fiable: mu={mu2:.4f}, std={s2:.4f}, weight={w2:.2f}")

    return threshold, reliable_mask, {
        "method": "gmm",
        "means": [float(mu1), float(mu2)],
        "stds": [float(s1), float(s2)],
        "weights": [float(w1), float(w2)],
    }


# -----------------------------------------------
# Método 3: Knee/Elbow Detection
# -----------------------------------------------
def knee_threshold(errors):
    """
    Detecta el "codo" en la curva de errores ordenados.
    El punto de inflexión máxima separa fiable de no fiable.
    """
    log("  [Knee] Buscando punto de inflexión...")

    sorted_errors = np.sort(errors)
    n = len(sorted_errors)

    # Normalizar a [0,1] para el análisis
    x = np.linspace(0, 1, n)
    y = (sorted_errors - sorted_errors[0]) / (sorted_errors[-1] - sorted_errors[0] + 1e-10)

    # Distancia perpendicular a la línea que conecta primer y último punto
    # Línea: desde (0, y[0]) hasta (1, y[-1])
    line_start = np.array([0, y[0]])
    line_end = np.array([1, y[-1]])
    line_vec = line_end - line_start
    line_len = np.linalg.norm(line_vec)
    line_unit = line_vec / line_len

    # Distancia de cada punto a la línea
    distances = np.zeros(n)
    for i in range(n):
        point = np.array([x[i], y[i]])
        vec = point - line_start
        proj = np.dot(vec, line_unit)
        closest = line_start + proj * line_unit
        distances[i] = np.linalg.norm(point - closest)

    # El knee es el punto con máxima distancia
    knee_idx = np.argmax(distances)
    threshold = sorted_errors[knee_idx]

    reliable_mask = errors < threshold
    n_reliable = reliable_mask.sum()
    log(f"  [Knee] Threshold: {threshold:.4f}, Fiables: {n_reliable} ({100*n_reliable/n:.1f}%)")

    return threshold, reliable_mask, {"method": "knee", "knee_percentile": float(100 * knee_idx / n)}


# -----------------------------------------------
# Método 4: Otsu's Method (adaptado)
# -----------------------------------------------
def otsu_threshold(errors, n_bins=256):
    """
    Adaptación de Otsu's method (usado en segmentación de imágenes)
    para encontrar el umbral óptimo que separa dos distribuciones.
    Minimiza la varianza intra-clase.
    """
    log("  [Otsu] Buscando threshold óptimo...")

    # Histograma
    hist, bin_edges = np.histogram(errors, bins=n_bins, density=True)
    bin_centers = (bin_edges[:-1] + bin_edges[1:]) / 2

    # Otsu's criterion
    total = hist.sum()
    best_threshold = 0
    best_variance = 0

    cumsum = np.cumsum(hist)
    cum_mean = np.cumsum(hist * bin_centers)
    global_mean = cum_mean[-1]

    for i in range(1, n_bins):
        w0 = cumsum[i]
        w1 = total - w0
        if w0 == 0 or w1 == 0:
            continue

        mu0 = cum_mean[i] / w0
        mu1 = (global_mean - cum_mean[i]) / w1

        variance = w0 * w1 * (mu0 - mu1) ** 2

        if variance > best_variance:
            best_variance = variance
            best_threshold = bin_centers[i]

    threshold = best_threshold
    reliable_mask = errors < threshold
    n_reliable = reliable_mask.sum()
    log(f"  [Otsu] Threshold: {threshold:.4f}, Fiables: {n_reliable} ({100*n_reliable/len(errors):.1f}%)")

    return threshold, reliable_mask, {"method": "otsu"}


# -----------------------------------------------
# Comparación y selección del mejor método
# -----------------------------------------------
def compare_and_select(errors, labels, dataset_name, fig_dir):
    """Ejecuta todos los métodos y selecciona el mejor automáticamente."""
    results = {}

    # Ejecutar todos los métodos
    methods = {
        "permutation": lambda: permutation_threshold(errors, labels),
        "gmm": lambda: gmm_threshold(errors),
        "knee": lambda: knee_threshold(errors),
        "otsu": lambda: otsu_threshold(errors),
        "p20_manual": lambda: (np.percentile(errors, 20),
                                errors < np.percentile(errors, 20),
                                {"method": "p20_manual"}),
    }

    for name, func in methods.items():
        try:
            threshold, mask, meta = func()
            results[name] = {
                "threshold": float(threshold),
                "n_reliable": int(mask.sum()),
                "pct_reliable": round(100 * mask.sum() / len(errors), 1),
                "meta": meta,
            }
        except Exception as e:
            log(f"  WARNING: {name} falló: {e}")

    # Seleccionar mejor método: el que da mayor silhouette score en los fiables
    best_method = "p20_manual"
    best_score = -1

    try:
        from sklearn.metrics import silhouette_score

        for name, res in results.items():
            mask = errors < res["threshold"]
            if mask.sum() > 100 and mask.sum() < len(errors) * 0.95:
                if len(np.unique(labels[mask])) > 1:
                    from sklearn.decomposition import PCA
                    # Usar errors como feature proxy
                    score = silhouette_score(
                        errors[mask].reshape(-1, 1),
                        labels[mask],
                        sample_size=min(5000, mask.sum()),
                    )
                    results[name]["silhouette"] = float(score)
                    if score > best_score:
                        best_score = score
                        best_method = name
    except Exception:
        # Si sklearn falla, usar GMM por defecto
        best_method = "gmm" if "gmm" in results else "p20_manual"

    log(f"\n  Mejor método: {best_method}")
    results["selected"] = best_method

    # Generar figura comparativa
    fig, axes = plt.subplots(1, len(results) - 1, figsize=(5 * (len(results) - 1), 5))
    if not hasattr(axes, "__len__"):
        axes = [axes]

    for ax, (name, res) in zip(axes, [(k, v) for k, v in results.items() if k != "selected"]):
        ax.hist(errors, bins=80, alpha=0.5, color="gray")
        ax.axvline(res["threshold"], color="red", linewidth=2, linestyle="--")
        title = f"{name}\n{res['pct_reliable']}% fiable"
        if name == best_method:
            title += " ★"
            ax.set_facecolor("#f0fff0")
        ax.set_title(title, fontsize=10)
        ax.set_xlabel("Consensus Error", fontsize=8)

    plt.suptitle(f"Comparación de thresholds — {dataset_name}", fontsize=13, fontweight="bold")
    plt.tight_layout()
    path = fig_dir / f"auto_threshold_{dataset_name}.png"
    plt.savefig(path, dpi=200, bbox_inches="tight")
    plt.close()
    log(f"  Figura: {path.name}")

    return results


def run_auto_threshold(dataset_name):
    """Ejecuta la selección automática de threshold para un dataset."""
    fc_dir = RESULTS_DIR / dataset_name / "flexconsensus"
    fig_dir = RESULTS_DIR / dataset_name / "figures"
    fig_dir.mkdir(parents=True, exist_ok=True)

    log(f"\n{'='*60}")
    log(f"AUTO-THRESHOLD: {dataset_name}")
    log(f"{'='*60}")

    # Cargar datos
    errors_file = fc_dir / "consensus_error.npy"
    labels_file = fc_dir / "cluster_labels.npy"

    if not errors_file.exists():
        log(f"ERROR: No se encontró {errors_file}")
        return False

    errors = np.load(errors_file)
    labels = np.load(labels_file) if labels_file.exists() else np.zeros(len(errors), dtype=int)

    # Comparar métodos
    results = compare_and_select(errors, labels, dataset_name, fig_dir)

    # Guardar reporte
    report_path = fig_dir / f"auto_threshold_report_{dataset_name}.json"
    with open(report_path, "w") as f:
        json.dump(results, f, indent=2)
    log(f"  Reporte: {report_path}")

    # Aplicar el mejor threshold
    selected = results["selected"]
    threshold = results[selected]["threshold"]
    mask = errors < threshold

    # Guardar partículas fiables filtradas
    consensus = np.load(fc_dir / "consensus_latents.npy")
    np.save(fc_dir / "auto_filtered_consensus.npy", consensus[mask])
    np.save(fc_dir / "auto_filtered_labels.npy", labels[mask])
    np.save(fc_dir / "auto_threshold_mask.npy", mask)

    log(f"\n  Threshold automático ({selected}): {threshold:.4f}")
    log(f"  Partículas fiables: {mask.sum():,} / {len(errors):,} ({100*mask.sum()/len(errors):.1f}%)")
    log(f"  Archivos guardados en {fc_dir}")

    return True


def main():
    parser = argparse.ArgumentParser(description="M4: Auto-threshold")
    parser.add_argument("--dataset", required=True, choices=ALL_DATASETS + ["all"])
    args = parser.parse_args()

    datasets = ALL_DATASETS if args.dataset == "all" else [args.dataset]
    for ds in datasets:
        run_auto_threshold(ds)


if __name__ == "__main__":
    main()
