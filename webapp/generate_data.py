"""
Genera datos simulados que replican los resultados del paper FlexConsensus
sobre el dataset IgG-RL de CryoBench.

Basado en:
- 50,000 partículas (similar al paper)
- 2 métodos: CryoDRGN y HetSIREN
- Espacio latente de 8 dimensiones (reducido a 3 para visualización con UMAP-like)
- ~20% de partículas con alto consenso (fiables)
- p-valor < 0.01 en test de Mantel
"""
import numpy as np
import json
import os

np.random.seed(42)

N_PARTICLES = 50000
N_CONFORMATIONS = 5  # Estados conformacionales del IgG-RL

# --- 1. Generar estados conformacionales ground truth ---
# Cada conformación es un cluster en el espacio latente
centers = np.array([
    [2.0, 1.5, 0.5],
    [-1.5, 2.0, -1.0],
    [-2.0, -1.5, 1.5],
    [1.0, -2.0, -0.5],
    [0.0, 0.0, 2.5],
])

# Asignar partículas a conformaciones (distribución no uniforme, como en datos reales)
weights = [0.30, 0.25, 0.20, 0.15, 0.10]
labels = np.random.choice(N_CONFORMATIONS, size=N_PARTICLES, p=weights)

# --- 2. Generar espacio latente CryoDRGN ---
latent_cryodrgn = np.zeros((N_PARTICLES, 3))
for i in range(N_CONFORMATIONS):
    mask = labels == i
    n = mask.sum()
    latent_cryodrgn[mask] = centers[i] + np.random.randn(n, 3) * 0.8

# Añadir rotación (los métodos producen espacios latentes rotados entre sí)
rotation = np.array([
    [0.85, -0.35, 0.39],
    [0.42, 0.90, -0.12],
    [-0.31, 0.27, 0.91],
])

# --- 3. Generar espacio latente HetSIREN ---
latent_hetsiren = np.zeros((N_PARTICLES, 3))
for i in range(N_CONFORMATIONS):
    mask = labels == i
    n = mask.sum()
    # HetSIREN tiene diferente varianza y rotación
    latent_hetsiren[mask] = (centers[i] @ rotation.T) + np.random.randn(n, 3) * 0.7

# --- 4. Generar espacio de consenso FlexConsensus ---
# El consenso alinea ambos espacios latentes
latent_consensus = np.zeros((N_PARTICLES, 3))
for i in range(N_CONFORMATIONS):
    mask = labels == i
    n = mask.sum()
    # El consenso reduce la varianza donde ambos métodos coinciden
    latent_consensus[mask] = centers[i] + np.random.randn(n, 3) * 0.5

# --- 5. Generar consensus error ---
# Partículas donde ambos métodos coinciden tienen bajo error
# ~20% fiables (bajo error), ~80% con error alto (como en el paper)
base_error = np.random.exponential(0.4, N_PARTICLES)

# Las partículas en conformaciones bien definidas tienen menor error
for i in range(N_CONFORMATIONS):
    mask = labels == i
    dist_to_center = np.linalg.norm(latent_consensus[mask] - centers[i], axis=1)
    base_error[mask] *= (0.5 + dist_to_center / dist_to_center.max())

# Normalizar entre 0 y 1
consensus_error = (base_error - base_error.min()) / (base_error.max() - base_error.min())

# --- 6. Test de Mantel (p-valor simulado) ---
# En el paper obtienen p < 0.01
mantel_r = 0.73  # Correlación de Mantel
mantel_p = 0.001  # p-valor

# --- 7. Métricas por conformación ---
metrics_per_conf = []
for i in range(N_CONFORMATIONS):
    mask = labels == i
    metrics_per_conf.append({
        "conformacion": i + 1,
        "n_particulas": int(mask.sum()),
        "error_medio": float(np.mean(consensus_error[mask])),
        "error_std": float(np.std(consensus_error[mask])),
        "porcentaje_fiable": float(np.mean(consensus_error[mask] < np.percentile(consensus_error, 20)) * 100),
    })

# --- 8. Guardar datos ---
output_dir = os.path.join(os.path.dirname(__file__), "data")
os.makedirs(output_dir, exist_ok=True)

# Subsample para la web (50k puntos es mucho para Plotly)
idx = np.random.choice(N_PARTICLES, size=5000, replace=False)
idx.sort()

def save_json(filename, data):
    with open(os.path.join(output_dir, filename), "w") as f:
        json.dump(data, f)

# Espacio latente CryoDRGN (subsampled)
save_json("latent_cryodrgn.json", {
    "x": latent_cryodrgn[idx, 0].tolist(),
    "y": latent_cryodrgn[idx, 1].tolist(),
    "z": latent_cryodrgn[idx, 2].tolist(),
    "labels": labels[idx].tolist(),
    "errors": consensus_error[idx].tolist(),
})

# Espacio latente HetSIREN (subsampled)
save_json("latent_hetsiren.json", {
    "x": latent_hetsiren[idx, 0].tolist(),
    "y": latent_hetsiren[idx, 1].tolist(),
    "z": latent_hetsiren[idx, 2].tolist(),
    "labels": labels[idx].tolist(),
    "errors": consensus_error[idx].tolist(),
})

# Espacio de consenso (subsampled)
save_json("latent_consensus.json", {
    "x": latent_consensus[idx, 0].tolist(),
    "y": latent_consensus[idx, 1].tolist(),
    "z": latent_consensus[idx, 2].tolist(),
    "labels": labels[idx].tolist(),
    "errors": consensus_error[idx].tolist(),
})

# Histograma de errores (todos los datos)
hist_counts, hist_edges = np.histogram(consensus_error, bins=60)
save_json("error_histogram.json", {
    "counts": hist_counts.tolist(),
    "edges": hist_edges.tolist(),
    "median": float(np.median(consensus_error)),
    "percentile_20": float(np.percentile(consensus_error, 20)),
    "percentile_80": float(np.percentile(consensus_error, 80)),
    "mean": float(np.mean(consensus_error)),
})

# Métricas generales
save_json("metrics.json", {
    "total_particles": N_PARTICLES,
    "n_methods": 2,
    "methods": ["CryoDRGN", "HetSIREN"],
    "latent_dim": 8,
    "mantel_r": mantel_r,
    "mantel_p": mantel_p,
    "n_conformations": N_CONFORMATIONS,
    "reliable_percentage": float(np.mean(consensus_error < np.percentile(consensus_error, 20)) * 100),
    "per_conformation": metrics_per_conf,
    "dataset": "IgG-RL (CryoBench)",
})

# Datos para comparación antes/después
fiable_mask = consensus_error[idx] < np.percentile(consensus_error, 20)
save_json("filtering_comparison.json", {
    "all": {
        "x": latent_consensus[idx, 0].tolist(),
        "y": latent_consensus[idx, 1].tolist(),
        "labels": labels[idx].tolist(),
    },
    "filtered": {
        "x": latent_consensus[idx][fiable_mask, 0].tolist(),
        "y": latent_consensus[idx][fiable_mask, 1].tolist(),
        "labels": labels[idx][fiable_mask].tolist(),
    },
    "n_all": int(len(idx)),
    "n_filtered": int(fiable_mask.sum()),
})

print(f"Datos generados exitosamente en {output_dir}/")
print(f"  - {N_PARTICLES} partículas totales")
print(f"  - {len(idx)} subsampled para visualización")
print(f"  - {N_CONFORMATIONS} conformaciones")
print(f"  - Error medio: {np.mean(consensus_error):.3f}")
print(f"  - Mantel r={mantel_r}, p={mantel_p}")
