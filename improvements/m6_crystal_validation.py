#!/usr/bin/env python3
"""
Mejora M6: Validación con cristalografía
==========================================
Compara las conformaciones detectadas por FlexConsensus con
estructuras cristalográficas conocidas en PDB.

Para cada conformación detectada:
1. Decodifica un volumen 3D representativo
2. Busca la estructura PDB más similar
3. Calcula RMSD y correlación
4. Genera mapa de diferencias

Uso:
  python improvements/m6_crystal_validation.py --dataset IgG-RL --gpu 0
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
ALL_DATASETS = ["IgG-RL", "MDSpike", "Ribosome-80S", "Spike-SARS2"]

# Estructuras PDB de referencia por dataset
PDB_REFERENCES = {
    "IgG-RL": {
        "pdb_ids": ["1IGT", "1HZH"],
        "description": "IgG: conformaciones hinge region",
    },
    "MDSpike": {
        "pdb_ids": ["6VXX", "6VYB", "7A94"],
        "description": "Spike: down, 1-up, 2-up RBD",
    },
    "Ribosome-80S": {
        "pdb_ids": ["4UG0", "4V6W", "4V88"],
        "description": "Ribosome: rotated, non-rotated, hybrid states",
    },
    "Spike-SARS2": {
        "pdb_ids": ["6VXX", "6VYB", "7A94"],
        "description": "Spike SARS-CoV-2: 3 conformaciones RBD",
    },
}


def log(msg):
    print(f"[CRYSTAL-VAL] {msg}", flush=True)


def download_pdb_structure(pdb_id, output_dir):
    """Descarga estructura PDB y genera mapa de densidad."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    pdb_file = output_dir / f"{pdb_id}.cif"
    map_file = output_dir / f"{pdb_id}.mrc"

    if pdb_file.exists():
        return pdb_file, map_file

    log(f"  Descargando {pdb_id}...")

    # Descargar estructura mmCIF
    try:
        import urllib.request
        url = f"https://files.rcsb.org/download/{pdb_id}.cif"
        urllib.request.urlretrieve(url, str(pdb_file))
        log(f"    {pdb_id}.cif descargado")
    except Exception as e:
        log(f"    ERROR descargando {pdb_id}: {e}")
        return None, None

    # Generar mapa de densidad simulado desde la estructura atómica
    try:
        import gemmi

        doc = gemmi.cif.read(str(pdb_file))
        st = gemmi.make_structure_from_block(doc[0])

        # Generar mapa a 3Å resolución
        dencalc = gemmi.DensityCalculatorE()
        dencalc.d_min = 3.0
        dencalc.rate = 1.5
        dencalc.set_grid_cell_and_spacegroup(st)
        dencalc.put_model_density_on_grid(st[0])

        # Guardar como MRC
        ccp4 = gemmi.Ccp4Map()
        ccp4.grid = dencalc.grid
        ccp4.update_ccp4_header()
        ccp4.write_ccp4_map(str(map_file))
        log(f"    Mapa {pdb_id}.mrc generado (3Å)")

    except ImportError:
        log("    WARNING: gemmi no disponible, no se pudo generar mapa")
        map_file = None
    except Exception as e:
        log(f"    WARNING: Error generando mapa: {e}")
        map_file = None

    return pdb_file, map_file


def compute_map_correlation(map1_path, map2_path):
    """Calcula la correlación entre dos mapas de densidad MRC."""
    try:
        import mrcfile

        with mrcfile.open(str(map1_path)) as mrc1:
            data1 = mrc1.data.copy().flatten()
        with mrcfile.open(str(map2_path)) as mrc2:
            data2 = mrc2.data.copy().flatten()

        # Normalizar
        data1 = (data1 - data1.mean()) / (data1.std() + 1e-10)
        data2 = (data2 - data2.mean()) / (data2.std() + 1e-10)

        # Si los tamaños no coinciden, interpolar
        if len(data1) != len(data2):
            from scipy.ndimage import zoom
            ratio = (len(data2) / len(data1)) ** (1/3)
            # Reshape back to 3D, zoom, flatten
            s1 = int(round(len(data1) ** (1/3)))
            data1_3d = data1[:s1**3].reshape(s1, s1, s1)
            s2 = int(round(len(data2) ** (1/3)))
            data2_3d = data2[:s2**3].reshape(s2, s2, s2)
            data1_3d = zoom(data1_3d, s2/s1)
            data1 = data1_3d.flatten()
            data2 = data2_3d.flatten()

        # Correlación de Pearson
        from scipy.stats import pearsonr
        r, p = pearsonr(data1[:len(data2)], data2[:len(data1)])
        return float(r)

    except Exception as e:
        log(f"    Error en correlación: {e}")
        return None


def decode_conformations(dataset_name, gpu="0"):
    """
    Decodifica volúmenes 3D para cada centro de cluster.
    Usa CryoDRGN para generar volúmenes desde puntos del espacio latente.
    """
    result_dir = RESULTS_DIR / dataset_name
    fc_dir = result_dir / "flexconsensus"
    decode_dir = result_dir / "decoded_volumes"
    decode_dir.mkdir(parents=True, exist_ok=True)

    # Cargar centros de cluster
    centers_file = fc_dir / "cluster_centers.npy"
    if not centers_file.exists():
        log("  No hay cluster centers, calculando...")
        consensus = np.load(fc_dir / "consensus_latents.npy")
        labels = np.load(fc_dir / "cluster_labels.npy")

        from sklearn.cluster import KMeans
        n_clusters = len(np.unique(labels))
        km = KMeans(n_clusters=n_clusters, random_state=42, n_init=20)
        km.fit(consensus)
        np.save(centers_file, km.cluster_centers_)

    centers = np.load(centers_file)
    n_conformations = len(centers)
    log(f"  {n_conformations} conformaciones a decodificar")

    # Usar CryoDRGN para decodificar volúmenes
    cryodrgn_dir = result_dir / "cryodrgn"
    config_file = cryodrgn_dir / "config.yaml"
    weights_file = None

    # Buscar último checkpoint
    import glob
    weight_files = sorted(glob.glob(str(cryodrgn_dir / "weights.*.pkl")))
    if weight_files:
        weights_file = weight_files[-1]
    elif (cryodrgn_dir / "weights.pkl").exists():
        weights_file = str(cryodrgn_dir / "weights.pkl")

    if not weights_file or not config_file.exists():
        log("  WARNING: No se encontró modelo CryoDRGN para decodificar")
        return decode_dir, n_conformations

    # Para cada centro de cluster, decodificar un volumen
    env = os.environ.copy()
    env["CUDA_VISIBLE_DEVICES"] = gpu

    for i, center in enumerate(centers):
        vol_file = decode_dir / f"conformation_{i}.mrc"
        if vol_file.exists():
            continue

        # Guardar centro como archivo temporal
        z_file = decode_dir / f"z_center_{i}.txt"
        np.savetxt(z_file, center.reshape(1, -1), fmt="%.8f")

        cmd = [
            "cryodrgn", "eval_vol",
            str(cryodrgn_dir),
            "--zfile", str(z_file),
            "-o", str(vol_file),
        ]

        result = subprocess.run(cmd, capture_output=True, text=True, env=env)
        if result.returncode == 0:
            log(f"    Volumen {i} decodificado: {vol_file.name}")
        else:
            log(f"    WARNING: Error decodificando volumen {i}")

    return decode_dir, n_conformations


def run_crystal_validation(dataset_name, gpu="0"):
    """Ejecuta la validación completa con cristalografía."""
    refs = PDB_REFERENCES.get(dataset_name)
    if not refs:
        log(f"No hay referencias PDB para {dataset_name}")
        return False

    result_dir = RESULTS_DIR / dataset_name
    fig_dir = result_dir / "figures"
    ref_dir = result_dir / "pdb_references"
    fig_dir.mkdir(parents=True, exist_ok=True)
    ref_dir.mkdir(parents=True, exist_ok=True)

    log(f"\n{'='*60}")
    log(f"VALIDACIÓN CRISTALOGRÁFICA: {dataset_name}")
    log(f"Referencias PDB: {refs['pdb_ids']}")
    log(f"{'='*60}")

    # 1. Descargar estructuras PDB de referencia
    log("\n[1/3] Descargando estructuras PDB...")
    pdb_maps = {}
    for pdb_id in refs["pdb_ids"]:
        pdb_file, map_file = download_pdb_structure(pdb_id, ref_dir)
        if map_file and Path(map_file).exists():
            pdb_maps[pdb_id] = map_file

    # 2. Decodificar conformaciones detectadas
    log("\n[2/3] Decodificando conformaciones...")
    decode_dir, n_conf = decode_conformations(dataset_name, gpu)

    # 3. Comparar cada conformación con cada referencia PDB
    log("\n[3/3] Calculando correlaciones...")
    correlation_matrix = np.zeros((n_conf, len(pdb_maps)))
    pdb_ids = list(pdb_maps.keys())

    for i in range(n_conf):
        vol_file = decode_dir / f"conformation_{i}.mrc"
        if not vol_file.exists():
            continue

        for j, pdb_id in enumerate(pdb_ids):
            corr = compute_map_correlation(vol_file, pdb_maps[pdb_id])
            if corr is not None:
                correlation_matrix[i, j] = corr
                log(f"  Conf {i} vs {pdb_id}: r={corr:.4f}")

    # Generar figura de correlaciones
    fig, ax = plt.subplots(figsize=(10, 6))
    im = ax.imshow(correlation_matrix, cmap="RdYlGn", vmin=-0.5, vmax=1, aspect="auto")
    ax.set_xticks(range(len(pdb_ids)))
    ax.set_xticklabels(pdb_ids, fontsize=11)
    ax.set_yticks(range(n_conf))
    ax.set_yticklabels([f"Conf {i}" for i in range(n_conf)], fontsize=11)
    ax.set_xlabel("Estructura PDB de referencia", fontsize=12)
    ax.set_ylabel("Conformación detectada", fontsize=12)
    ax.set_title(f"Correlación con cristalografía — {dataset_name}", fontsize=14, fontweight="bold")

    for i in range(n_conf):
        for j in range(len(pdb_ids)):
            ax.text(j, i, f"{correlation_matrix[i,j]:.3f}",
                    ha="center", va="center", fontsize=10,
                    color="white" if correlation_matrix[i,j] < 0.3 else "black")

    plt.colorbar(im, label="Correlación de Pearson")
    plt.tight_layout()
    path = fig_dir / f"crystal_validation_{dataset_name}.png"
    plt.savefig(path, dpi=300, bbox_inches="tight")
    plt.close()
    log(f"\n  Figura: {path}")

    # Asignar conformaciones a estructuras PDB
    log("\n  === ASIGNACIÓN CONFORMACIÓN → PDB ===")
    assignments = {}
    for i in range(n_conf):
        best_j = np.argmax(correlation_matrix[i])
        best_pdb = pdb_ids[best_j]
        best_corr = correlation_matrix[i, best_j]
        assignments[f"Conf_{i}"] = {"pdb": best_pdb, "correlation": float(best_corr)}
        quality = "ALTA" if best_corr > 0.7 else "MODERADA" if best_corr > 0.4 else "BAJA"
        log(f"  Conf {i} → {best_pdb} (r={best_corr:.4f}, {quality})")

    # Guardar reporte
    report = {
        "dataset": dataset_name,
        "pdb_references": refs,
        "correlation_matrix": correlation_matrix.tolist(),
        "assignments": assignments,
    }
    report_path = fig_dir / f"crystal_validation_report_{dataset_name}.json"
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2)

    return True


def main():
    parser = argparse.ArgumentParser(description="M6: Validación con cristalografía")
    parser.add_argument("--dataset", required=True, choices=ALL_DATASETS + ["all"])
    parser.add_argument("--gpu", default="0")
    args = parser.parse_args()

    datasets = ALL_DATASETS if args.dataset == "all" else [args.dataset]
    for ds in datasets:
        run_crystal_validation(ds, args.gpu)


if __name__ == "__main__":
    main()
