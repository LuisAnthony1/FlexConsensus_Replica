#!/usr/bin/env python3
"""
Mejora M1: Agregar 3DFlex como tercer método
==============================================
Integra 3DFlex (CryoSPARC) como tercer espacio latente para FlexConsensus.
Comparar 3 métodos simultáneos en vez de 2 da mayor robustez al consenso.

3DFlex modela la flexibilidad como un campo de deformación continuo
sobre una estructura canónica, usando bases de movimiento aprendidas.

Requiere: CryoSPARC 4.5+ con licencia académica

Uso:
  python improvements/m1_3dflex.py --dataset IgG-RL --cryosparc-project P1 --gpu 0
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

# 3DFlex necesita CryoSPARC
CRYOSPARC_CLI = os.environ.get("CRYOSPARC_CLI", "cryosparcm")

FLEX3D_CONFIGS = {
    "IgG-RL": {"K": 4, "epochs": 20, "description": "IgG-RL: 3DFlex con 4 bases"},
    "MDSpike": {"K": 8, "epochs": 20, "description": "MDSpike: 3DFlex con 8 bases"},
    "Ribosome-80S": {"K": 10, "epochs": 20, "description": "Ribosome 80S: 3DFlex con 10 bases"},
    "Spike-SARS2": {"K": 10, "epochs": 20, "description": "SARS-CoV-2: 3DFlex con 10 bases"},
}


def log(msg):
    print(f"[3DFLEX] {msg}", flush=True)


def run_3dflex_via_cryosparc(dataset_name, cryosparc_project, gpu="0"):
    """
    Ejecuta 3DFlex a través de la API de CryoSPARC.
    CryoSPARC debe estar corriendo como servicio.
    """
    config = FLEX3D_CONFIGS[dataset_name]
    result_dir = RESULTS_DIR / dataset_name
    flex3d_dir = result_dir / "3dflex"
    flex3d_dir.mkdir(parents=True, exist_ok=True)

    log(f"=== 3DFlex: {config['description']} ===")

    # Verificar si ya completado
    latent_output = flex3d_dir / "latent_space.txt"
    if latent_output.exists():
        log(f"3DFlex ya completado para {dataset_name}. Saltando.")
        return True

    # Verificar CryoSPARC
    try:
        from cryosparc.tools import CryoSPARC

        # Conectar a la instancia de CryoSPARC
        cs_host = os.environ.get("CRYOSPARC_HOST", "localhost")
        cs_port = int(os.environ.get("CRYOSPARC_PORT", 39000))
        cs_email = os.environ.get("CRYOSPARC_EMAIL", "")
        cs_password = os.environ.get("CRYOSPARC_PASSWORD", "")

        cs = CryoSPARC(
            host=cs_host,
            base_port=cs_port,
            email=cs_email,
            password=cs_password,
        )
        log(f"  Conectado a CryoSPARC en {cs_host}:{cs_port}")

    except ImportError:
        log("  CryoSPARC Python API no disponible.")
        log("  Ejecutando via línea de comandos...")
        return run_3dflex_via_cli(dataset_name, cryosparc_project, config, flex3d_dir, gpu)

    # Obtener el proyecto
    project = cs.find_project(cryosparc_project)
    workspace = project.find_workspace("W1")  # Default workspace

    # Buscar partículas preprocesadas en CryoSPARC
    # (asumimos que ya fueron importadas previamente)
    preproc_dir = result_dir / "preprocessed"
    particles_file = list(preproc_dir.glob("particles_*.mrcs"))
    if not particles_file:
        log("  ERROR: No se encontraron partículas preprocesadas")
        return False

    # 1. Importar partículas si no existen en el proyecto
    log("  Importando partículas a CryoSPARC...")
    import_job = workspace.create_job("import_particles")
    import_job.set_param("particle_meta_path", str(preproc_dir / "*.star"))
    import_job.set_param("particle_blob_path", str(particles_file[0]))
    import_job.queue(lane="default", gpus=[int(g) for g in gpu.split(",")])
    import_job.wait_for_done()

    particles_output = import_job.load_output("imported_particles")
    log(f"  Partículas importadas: {len(particles_output)} ")

    # 2. 3D Flex Mesh Prep
    log("  Preparando mesh para 3DFlex...")
    mesh_job = workspace.create_job("flex_mesh_prep")
    mesh_job.connect("particles", import_job, "imported_particles")
    mesh_job.queue(lane="default")
    mesh_job.wait_for_done()

    # 3. 3D Flex Train
    log(f"  Entrenando 3DFlex (K={config['K']}, epochs={config['epochs']})...")
    train_job = workspace.create_job("flex_train")
    train_job.connect("particles", import_job, "imported_particles")
    train_job.connect("mesh", mesh_job, "mesh")
    train_job.set_param("flex_K", config["K"])
    train_job.set_param("flex_num_iters", config["epochs"])
    train_job.queue(lane="default", gpus=[int(g) for g in gpu.split(",")])
    train_job.wait_for_done()

    # 4. Extraer espacio latente
    log("  Extrayendo espacio latente de 3DFlex...")
    result = train_job.load_output("flex_particles")

    # Los coeficientes de deformación son el espacio latente
    latent_data = np.array([p["flex_coeffs"] for p in result])
    np.savetxt(latent_output, latent_data, fmt="%.8f")
    log(f"  Espacio latente 3DFlex: {latent_output} (shape: {latent_data.shape})")

    # Guardar metadatos
    run_meta = {
        "method": "3DFlex",
        "dataset": dataset_name,
        "config": config,
        "cryosparc_project": cryosparc_project,
        "latent_shape": list(latent_data.shape),
    }
    with open(flex3d_dir / "run_meta.json", "w") as f:
        json.dump(run_meta, f, indent=2)

    log(f"  3DFlex completado para {dataset_name}!")
    return True


def run_3dflex_via_cli(dataset_name, project_id, config, flex3d_dir, gpu):
    """Ejecuta 3DFlex via CryoSPARC CLI cuando la API Python no está disponible."""
    log("  Usando CryoSPARC CLI...")

    # Verificar que cryosparcm está disponible
    try:
        subprocess.run([CRYOSPARC_CLI, "cli"], capture_output=True, check=True)
    except (FileNotFoundError, subprocess.CalledProcessError):
        log("  ERROR: cryosparcm no encontrado.")
        log("  Configura CRYOSPARC_CLI o instala CryoSPARC.")
        log("  Documentación: https://guide.cryosparc.com/")
        return False

    # Script CryoSPARC CLI
    cli_script = f"""
import json
from cryosparc_compute import client

# Conectar
cs = client.CommandClient(host='localhost', port=39002)

# Crear job 3DFlex Train
job = cs.make_job('{project_id}', 'W1', 'flex_train')
cs.set_job_param('{project_id}', job['uid'], 'flex_K', {config['K']})
cs.set_job_param('{project_id}', job['uid'], 'flex_num_iters', {config['epochs']})
cs.enqueue_job('{project_id}', job['uid'], lane='default', gpus=[{gpu}])

print(json.dumps({{'job_uid': job['uid']}}))
"""

    script_path = flex3d_dir / "run_3dflex.py"
    with open(script_path, "w") as f:
        f.write(cli_script)

    result = subprocess.run(
        [CRYOSPARC_CLI, "cli", str(script_path)],
        capture_output=True, text=True,
    )

    if result.returncode != 0:
        log(f"  ERROR: {result.stderr[:300]}")
        return False

    log("  Job de 3DFlex enviado. Monitorea en CryoSPARC Web UI.")
    log(f"  Una vez completado, exporta el espacio latente a:")
    log(f"    {flex3d_dir / 'latent_space.txt'}")
    return True


def main():
    parser = argparse.ArgumentParser(description="M1: 3DFlex como tercer método")
    parser.add_argument("--dataset", required=True,
                        choices=list(FLEX3D_CONFIGS.keys()) + ["all"])
    parser.add_argument("--cryosparc-project", default="P1", help="CryoSPARC project ID")
    parser.add_argument("--gpu", default="0")
    args = parser.parse_args()

    datasets = list(FLEX3D_CONFIGS.keys()) if args.dataset == "all" else [args.dataset]
    for ds in datasets:
        run_3dflex_via_cryosparc(ds, args.cryosparc_project, args.gpu)


if __name__ == "__main__":
    main()
