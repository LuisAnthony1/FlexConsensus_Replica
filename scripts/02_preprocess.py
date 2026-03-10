#!/usr/bin/env python3
"""
FlexConsensus - FASE 1: Preprocesamiento de partículas Cryo-EM
==============================================================
Prepara las partículas de cada dataset para CryoDRGN y HetSIREN.

Pasos:
  1. Importar partículas (.mrcs/.star)
  2. Estimar CTF
  3. Extraer poses (rotaciones + traslaciones)
  4. Downsample a resolución manejable (128px)
  5. Generar archivos de entrada para cada método

Uso:
  python scripts/02_preprocess.py --dataset cryobench
  python scripts/02_preprocess.py --dataset empiar10028
  python scripts/02_preprocess.py --dataset empiar10492
  python scripts/02_preprocess.py --dataset all
"""

import argparse
import os
import sys
import subprocess
import glob
import shutil
import numpy as np
from pathlib import Path

# -----------------------------------------------
# Configuración
# -----------------------------------------------
PROJECT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_DIR / "data"
RESULTS_DIR = PROJECT_DIR / "results"

DATASETS = {
    "IgG-RL": {
        "data_dir": DATA_DIR / "cryobench" / "IgG-RL",
        "results_dir": RESULTS_DIR / "IgG-RL",
        "box_size": 128,          # Downsample target
        "pixel_size": None,       # Auto-detect from star file
        "has_ground_truth": True,  # CryoBench tiene ground truth
        "description": "IgG-RL (CryoBench) - Synthetic, 1D conformational landscape",
    },
    "MDSpike": {
        "data_dir": DATA_DIR / "cryobench" / "MDSpike",
        "results_dir": RESULTS_DIR / "MDSpike",
        "box_size": 128,
        "pixel_size": None,
        "has_ground_truth": True,
        "description": "MDSpike (CryoBench) - MD simulation of SARS-CoV-2 Spike",
    },
    "Ribosome-80S": {
        "data_dir": DATA_DIR / "empiar_10028",
        "results_dir": RESULTS_DIR / "Ribosome-80S",
        "box_size": 128,
        "pixel_size": 1.34,       # Angstroms/pixel from EMPIAR
        "has_ground_truth": False,
        "description": "Ribosome 80S (EMPIAR-10028) - Real experimental data",
    },
    "Spike-SARS2": {
        "data_dir": DATA_DIR / "empiar_10492",
        "results_dir": RESULTS_DIR / "Spike-SARS2",
        "box_size": 128,
        "pixel_size": 1.058,
        "has_ground_truth": False,
        "description": "SARS-CoV-2 Spike (EMPIAR-10492) - Replacement for D614G",
    },
}


def log(msg):
    print(f"[PREPROCESS] {msg}", flush=True)


# -----------------------------------------------
# Funciones de preprocesamiento
# -----------------------------------------------
def find_star_files(data_dir):
    """Encuentra archivos .star en el directorio de datos."""
    patterns = ["**/*.star", "**/*particles*.star", "**/*refined*.star"]
    for pattern in patterns:
        files = sorted(glob.glob(str(data_dir / pattern), recursive=True))
        if files:
            return files
    return []


def find_mrcs_files(data_dir):
    """Encuentra archivos .mrcs en el directorio de datos."""
    files = sorted(glob.glob(str(data_dir / "**/*.mrcs"), recursive=True))
    if not files:
        files = sorted(glob.glob(str(data_dir / "**/*.mrc"), recursive=True))
    return files


def detect_pixel_size(star_file):
    """Detecta pixel size desde un archivo .star."""
    try:
        import starfile
        df = starfile.read(star_file)
        if isinstance(df, dict):
            # RELION 3.1+ format
            if "optics" in df:
                return float(df["optics"]["rlnImagePixelSize"].iloc[0])
        else:
            if "rlnImagePixelSize" in df.columns:
                return float(df["rlnImagePixelSize"].iloc[0])
            elif "rlnDetectorPixelSize" in df.columns:
                mag = float(df["rlnMagnification"].iloc[0]) if "rlnMagnification" in df.columns else 1.0
                return float(df["rlnDetectorPixelSize"].iloc[0]) / mag * 1e4
    except Exception as e:
        log(f"  Warning: No se pudo detectar pixel size: {e}")
    return None


def downsample_particles(input_mrcs, output_mrcs, target_size):
    """Downsample partículas usando CryoDRGN."""
    cmd = [
        "cryodrgn", "downsample",
        str(input_mrcs),
        "-D", str(target_size),
        "-o", str(output_mrcs),
        "--chunk", "10000",
    ]
    log(f"  Downsampling: {Path(input_mrcs).name} -> {target_size}px")
    subprocess.run(cmd, check=True, capture_output=True, text=True)
    return output_mrcs


def parse_poses(star_file, output_pkl, box_size=None, pixel_size=None):
    """Extrae poses (rotaciones + traslaciones) del archivo .star."""
    cmd = ["cryodrgn", "parse_pose_star", str(star_file), "-o", str(output_pkl)]
    if box_size:
        cmd.extend(["-D", str(box_size)])
    if pixel_size:
        cmd.extend(["--Apix", str(pixel_size)])
    log(f"  Parsing poses -> {Path(output_pkl).name}")
    subprocess.run(cmd, check=True, capture_output=True, text=True)
    return output_pkl


def parse_ctf(star_file, output_pkl, box_size=None, pixel_size=None):
    """Extrae parámetros CTF del archivo .star."""
    cmd = ["cryodrgn", "parse_ctf_star", str(star_file), "-o", str(output_pkl)]
    if box_size:
        cmd.extend(["-D", str(box_size)])
    if pixel_size:
        cmd.extend(["--Apix", str(pixel_size)])
    log(f"  Parsing CTF -> {Path(output_pkl).name}")
    subprocess.run(cmd, check=True, capture_output=True, text=True)
    return output_pkl


def preprocess_cryobench_dataset(name, config):
    """Preprocesa un dataset de CryoBench (ya tiene particles + ground truth)."""
    data_dir = config["data_dir"]
    out_dir = config["results_dir"]
    box_size = config["box_size"]

    log(f"=== Preprocesando {name} ===")
    log(f"  Origen: {data_dir}")
    log(f"  Destino: {out_dir}")

    # Crear directorios de salida
    preproc_dir = out_dir / "preprocessed"
    preproc_dir.mkdir(parents=True, exist_ok=True)

    # Buscar archivos
    star_files = find_star_files(data_dir)
    mrcs_files = find_mrcs_files(data_dir)

    if not star_files and not mrcs_files:
        log(f"  ERROR: No se encontraron archivos .star ni .mrcs en {data_dir}")
        log(f"  Ejecuta primero: bash scripts/01_download_data.sh --cryobench")
        return False

    log(f"  Encontrados: {len(star_files)} .star, {len(mrcs_files)} .mrcs")

    # Usar el primer .star como referencia
    if star_files:
        main_star = star_files[0]
        log(f"  Star principal: {Path(main_star).name}")

        # Detectar pixel size
        pixel_size = config["pixel_size"] or detect_pixel_size(main_star)
        if pixel_size:
            log(f"  Pixel size: {pixel_size} Å/px")

        # Parse poses
        poses_pkl = preproc_dir / "poses.pkl"
        if not poses_pkl.exists():
            parse_poses(main_star, poses_pkl, box_size, pixel_size)
        else:
            log(f"  Poses ya existen: {poses_pkl.name}")

        # Parse CTF
        ctf_pkl = preproc_dir / "ctf.pkl"
        if not ctf_pkl.exists():
            parse_ctf(main_star, ctf_pkl, box_size, pixel_size)
        else:
            log(f"  CTF ya existe: {ctf_pkl.name}")

    # Buscar o crear particles downsampled
    if mrcs_files:
        main_mrcs = mrcs_files[0]
        ds_mrcs = preproc_dir / f"particles_{box_size}.mrcs"
        if not ds_mrcs.exists():
            downsample_particles(main_mrcs, ds_mrcs, box_size)
        else:
            log(f"  Particles downsampled ya existen: {ds_mrcs.name}")

    # Copiar ground truth si existe
    if config["has_ground_truth"]:
        gt_files = glob.glob(str(data_dir / "**/*ground_truth*"), recursive=True)
        gt_files += glob.glob(str(data_dir / "**/*gt*"), recursive=True)
        gt_files += glob.glob(str(data_dir / "**/*labels*"), recursive=True)
        gt_files += glob.glob(str(data_dir / "**/*conformations*"), recursive=True)
        for gt in gt_files:
            dest = preproc_dir / Path(gt).name
            if not dest.exists():
                shutil.copy2(gt, dest)
                log(f"  Ground truth copiado: {Path(gt).name}")

    # Escribir metadatos del preprocesamiento
    meta = {
        "dataset": name,
        "box_size": box_size,
        "pixel_size": pixel_size,
        "n_star_files": len(star_files),
        "n_mrcs_files": len(mrcs_files),
        "has_ground_truth": config["has_ground_truth"],
    }
    import json
    with open(preproc_dir / "preprocess_meta.json", "w") as f:
        json.dump(meta, f, indent=2)

    log(f"  Preprocesamiento de {name} completado!")
    return True


def preprocess_empiar_dataset(name, config):
    """Preprocesa un dataset EMPIAR (datos experimentales reales)."""
    data_dir = config["data_dir"]
    out_dir = config["results_dir"]
    box_size = config["box_size"]
    pixel_size = config["pixel_size"]

    log(f"=== Preprocesando {name} (EMPIAR) ===")
    log(f"  Origen: {data_dir}")
    log(f"  Destino: {out_dir}")

    preproc_dir = out_dir / "preprocessed"
    preproc_dir.mkdir(parents=True, exist_ok=True)

    # Buscar archivos
    star_files = find_star_files(data_dir)
    mrcs_files = find_mrcs_files(data_dir)

    if not star_files and not mrcs_files:
        log(f"  ERROR: No se encontraron datos en {data_dir}")
        log(f"  Ejecuta primero: bash scripts/01_download_data.sh --empiar10028")
        return False

    log(f"  Encontrados: {len(star_files)} .star, {len(mrcs_files)} .mrcs")

    # Para datos EMPIAR, necesitamos primero hacer un consenso de alineamientos
    # Esto normalmente se hace en CryoSPARC o RELION
    if star_files:
        main_star = star_files[0]
        log(f"  Star principal: {Path(main_star).name}")
        log(f"  Pixel size: {pixel_size} Å/px")

        # Parse poses
        poses_pkl = preproc_dir / "poses.pkl"
        if not poses_pkl.exists():
            parse_poses(main_star, poses_pkl, box_size, pixel_size)

        # Parse CTF
        ctf_pkl = preproc_dir / "ctf.pkl"
        if not ctf_pkl.exists():
            parse_ctf(main_star, ctf_pkl, box_size, pixel_size)

    # Downsample
    if mrcs_files:
        # Si hay multiples .mrcs, crear un txt apuntando a todos
        if len(mrcs_files) > 1:
            txt_file = preproc_dir / "particles_list.txt"
            with open(txt_file, "w") as f:
                for m in mrcs_files:
                    f.write(f"{m}\n")
            input_particles = txt_file
        else:
            input_particles = mrcs_files[0]

        ds_mrcs = preproc_dir / f"particles_{box_size}.mrcs"
        if not ds_mrcs.exists():
            downsample_particles(input_particles, ds_mrcs, box_size)

    # Metadatos
    import json
    meta = {
        "dataset": name,
        "box_size": box_size,
        "pixel_size": pixel_size,
        "n_star_files": len(star_files),
        "n_mrcs_files": len(mrcs_files),
        "has_ground_truth": False,
    }
    with open(preproc_dir / "preprocess_meta.json", "w") as f:
        json.dump(meta, f, indent=2)

    log(f"  Preprocesamiento de {name} completado!")
    return True


# -----------------------------------------------
# Main
# -----------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="FASE 1: Preprocesamiento de partículas")
    parser.add_argument("--dataset", required=True,
                        choices=["cryobench", "empiar10028", "empiar10492", "all"],
                        help="Dataset a preprocesar")
    args = parser.parse_args()

    targets = []
    if args.dataset in ("cryobench", "all"):
        targets.extend(["IgG-RL", "MDSpike"])
    if args.dataset in ("empiar10028", "all"):
        targets.append("Ribosome-80S")
    if args.dataset in ("empiar10492", "all"):
        targets.append("Spike-SARS2")

    log(f"Datasets a procesar: {targets}")
    results = {}

    for name in targets:
        config = DATASETS[name]
        log(f"\n{'='*60}")
        log(config["description"])
        log(f"{'='*60}")

        if config["has_ground_truth"]:
            ok = preprocess_cryobench_dataset(name, config)
        else:
            ok = preprocess_empiar_dataset(name, config)

        results[name] = "OK" if ok else "FAILED"

    log("\n=== RESUMEN DE PREPROCESAMIENTO ===")
    for name, status in results.items():
        log(f"  {name}: {status}")

    log("\nSiguiente paso:")
    log("  python scripts/03_run_hetsiren.py --dataset IgG-RL")
    log("  python scripts/04_run_cryodrgn.py --dataset IgG-RL")


if __name__ == "__main__":
    main()
