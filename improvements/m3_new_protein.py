#!/usr/bin/env python3
"""
Mejora M3: Aplicar FlexConsensus a una proteína nueva no estudiada
===================================================================
Aplica el pipeline completo a una proteína farmacológicamente relevante
que NO fue analizada en el paper original.

Candidatas:
  1. TRPV1 (EMPIAR-10005) - Canal iónico, target para dolor
  2. GroEL-GroES (EMPIAR-10034) - Chaperona, modelo de alosterismo
  3. Spliceosome (EMPIAR-10180) - Maquinaria de splicing, conformaciones complejas
  4. ABC Transporter (EMPIAR-10061) - Resistencia a drogas, múltiples estados

Uso:
  python improvements/m3_new_protein.py --protein trpv1 --gpu 0
  python improvements/m3_new_protein.py --protein groEL --gpu 0
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
SCRIPTS_DIR = PROJECT_DIR / "scripts"

# Proteínas candidatas con relevancia farmacológica
NEW_PROTEINS = {
    "trpv1": {
        "name": "TRPV1 Ion Channel",
        "empiar_id": "EMPIAR-10005",
        "pdb_ids": ["3J5P", "3J5Q", "3J5R"],
        "relevance": "Target para tratamiento del dolor. Receptor de capsaicina.",
        "expected_conformations": ["Apo (cerrado)", "Capsaicin-bound", "RTX-bound (abierto)"],
        "estimated_size_gb": 30,
        "box_size": 128,
        "pixel_size": 1.22,
        "results_name": "TRPV1",
    },
    "groEL": {
        "name": "GroEL-GroES Chaperonin",
        "empiar_id": "EMPIAR-10034",
        "pdb_ids": ["4HEL", "1AON"],
        "relevance": "Chaperona molecular. Modelo clásico de alosterismo cooperativo.",
        "expected_conformations": ["Tense (T)", "Relaxed (R)", "GroES-bound"],
        "estimated_size_gb": 15,
        "box_size": 128,
        "pixel_size": 1.23,
        "results_name": "GroEL-GroES",
    },
    "spliceosome": {
        "name": "Spliceosome Complex",
        "empiar_id": "EMPIAR-10180",
        "pdb_ids": ["5LJ3", "5LJ5"],
        "relevance": "Maquinaria de splicing del ARN. Múltiples estados conformacionales.",
        "expected_conformations": ["Pre-catalytic", "Catalytic step I", "Post-catalytic"],
        "estimated_size_gb": 50,
        "box_size": 128,
        "pixel_size": 1.4,
        "results_name": "Spliceosome",
    },
    "abc_transporter": {
        "name": "ABC Transporter",
        "empiar_id": "EMPIAR-10061",
        "pdb_ids": ["5UAK", "5UAR"],
        "relevance": "Resistencia a drogas en cáncer. Bomba de eflujo multi-droga.",
        "expected_conformations": ["Inward-facing", "Outward-facing", "Occluded"],
        "estimated_size_gb": 20,
        "box_size": 128,
        "pixel_size": 1.1,
        "results_name": "ABC-Transporter",
    },
}


def log(msg):
    print(f"[NEW-PROTEIN] {msg}", flush=True)


def download_empiar(empiar_id, output_dir):
    """Descarga datos de EMPIAR."""
    empiar_num = empiar_id.split("-")[1]
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if (output_dir / ".download_complete").exists():
        log(f"  {empiar_id} ya descargado.")
        return True

    log(f"  Descargando {empiar_id}...")

    # Intentar con Aspera primero (rápido)
    ascp_cmd = [
        "ascp", "-QT", "-l", "500M", "-P", "33001",
        "-i", os.path.expanduser("~/.aspera/connect/etc/asperaweb_id_dsa.openssh"),
        f"era-fasp@fasp.ebi.ac.uk:/empiar/world_availability/{empiar_num}/",
        str(output_dir),
    ]

    result = subprocess.run(ascp_cmd, capture_output=True, text=True)
    if result.returncode != 0:
        # Fallback a wget
        log("  Aspera no disponible, usando wget...")
        wget_cmd = [
            "wget", "-r", "-nH", "--cut-dirs=5", "--no-parent", "-q", "--show-progress",
            f"ftp://ftp.ebi.ac.uk/empiar/world_availability/{empiar_num}/data/",
            "-P", str(output_dir),
        ]
        result = subprocess.run(wget_cmd, capture_output=True, text=True)
        if result.returncode != 0:
            log(f"  ERROR descargando: {result.stderr[:200]}")
            return False

    (output_dir / ".download_complete").touch()
    log(f"  {empiar_id} descargado!")
    return True


def run_full_pipeline(protein_key, gpu="0"):
    """Ejecuta el pipeline completo para una proteína nueva."""
    config = NEW_PROTEINS[protein_key]
    dataset_name = config["results_name"]
    data_dir = PROJECT_DIR / "data" / f"empiar_{config['empiar_id'].split('-')[1]}"
    result_dir = RESULTS_DIR / dataset_name

    log(f"\n{'='*60}")
    log(f"PROTEÍNA NUEVA: {config['name']}")
    log(f"EMPIAR: {config['empiar_id']}")
    log(f"Relevancia: {config['relevance']}")
    log(f"Conformaciones esperadas: {config['expected_conformations']}")
    log(f"{'='*60}")

    # 1. Descargar datos
    log("\n[1/5] Descargando datos...")
    if not download_empiar(config["empiar_id"], data_dir):
        return False

    # 2. Crear estructura de resultados
    for subdir in ["preprocessed", "hetsiren", "cryodrgn", "flexconsensus", "figures"]:
        (result_dir / subdir).mkdir(parents=True, exist_ok=True)

    # Crear archivo de metadata para el preprocesamiento
    meta = {
        "dataset": dataset_name,
        "box_size": config["box_size"],
        "pixel_size": config["pixel_size"],
        "empiar_id": config["empiar_id"],
        "has_ground_truth": False,
    }
    with open(result_dir / "preprocessed" / "preprocess_meta.json", "w") as f:
        json.dump(meta, f, indent=2)

    # 3. Preprocesar (reusar script existente)
    log("\n[2/5] Preprocesando...")

    # Buscar star files en los datos descargados
    import glob
    star_files = glob.glob(str(data_dir / "**/*.star"), recursive=True)
    mrcs_files = glob.glob(str(data_dir / "**/*.mrcs"), recursive=True)
    log(f"  Encontrados: {len(star_files)} .star, {len(mrcs_files)} .mrcs")

    if star_files:
        # Parse poses y CTF
        main_star = star_files[0]
        preproc_dir = result_dir / "preprocessed"

        # Downsample
        if mrcs_files:
            ds_mrcs = preproc_dir / f"particles_{config['box_size']}.mrcs"
            if not ds_mrcs.exists():
                cmd = [
                    "cryodrgn", "downsample", mrcs_files[0],
                    "-D", str(config["box_size"]),
                    "-o", str(ds_mrcs),
                    "--chunk", "10000",
                ]
                subprocess.run(cmd, capture_output=True, text=True)

        # Poses
        poses_pkl = preproc_dir / "poses.pkl"
        if not poses_pkl.exists():
            cmd = ["cryodrgn", "parse_pose_star", main_star, "-o", str(poses_pkl)]
            if config["pixel_size"]:
                cmd.extend(["--Apix", str(config["pixel_size"])])
            subprocess.run(cmd, capture_output=True, text=True)

        # CTF
        ctf_pkl = preproc_dir / "ctf.pkl"
        if not ctf_pkl.exists():
            cmd = ["cryodrgn", "parse_ctf_star", main_star, "-o", str(ctf_pkl)]
            if config["pixel_size"]:
                cmd.extend(["--Apix", str(config["pixel_size"])])
            subprocess.run(cmd, capture_output=True, text=True)

    # 4. Ejecutar HetSIREN + CryoDRGN
    log("\n[3/5] Ejecutando HetSIREN...")
    subprocess.run(
        [sys.executable, str(SCRIPTS_DIR / "03_run_hetsiren.py"),
         "--dataset", dataset_name, "--gpu", gpu],
        text=True,
    )

    log("\n[4/5] Ejecutando CryoDRGN...")
    subprocess.run(
        [sys.executable, str(SCRIPTS_DIR / "04_run_cryodrgn.py"),
         "--dataset", dataset_name, "--gpu", gpu],
        text=True,
    )

    # 5. FlexConsensus
    log("\n[5/5] Ejecutando FlexConsensus...")
    subprocess.run(
        [sys.executable, str(SCRIPTS_DIR / "05_run_flexconsensus.py"),
         "--dataset", dataset_name, "--gpu", gpu],
        text=True,
    )

    # Validación
    log("\n  Ejecutando validación...")
    subprocess.run(
        [sys.executable, str(SCRIPTS_DIR / "06_validate.py"),
         "--dataset", dataset_name],
        text=True,
    )

    # Comparar con conformaciones esperadas
    log(f"\n  === ANÁLISIS DE {config['name']} ===")
    log(f"  Conformaciones esperadas (literatura): {config['expected_conformations']}")
    fc_meta = result_dir / "flexconsensus" / "run_meta.json"
    if fc_meta.exists():
        with open(fc_meta) as f:
            fc_data = json.load(f)
        log(f"  Conformaciones detectadas: {fc_data.get('n_conformations', '?')}")
    log(f"  PDB de referencia: {config['pdb_ids']}")
    log(f"  Figuras en: {result_dir / 'figures'}")

    return True


def main():
    parser = argparse.ArgumentParser(description="M3: Proteína nueva no estudiada")
    parser.add_argument("--protein", required=True,
                        choices=list(NEW_PROTEINS.keys()),
                        help="Proteína a analizar")
    parser.add_argument("--gpu", default="0")
    parser.add_argument("--list", action="store_true", help="Listar proteínas disponibles")
    args = parser.parse_args()

    if args.list:
        for key, cfg in NEW_PROTEINS.items():
            print(f"\n{key}:")
            print(f"  {cfg['name']} ({cfg['empiar_id']})")
            print(f"  {cfg['relevance']}")
            print(f"  Tamaño estimado: {cfg['estimated_size_gb']} GB")
        return

    run_full_pipeline(args.protein, args.gpu)


if __name__ == "__main__":
    main()
