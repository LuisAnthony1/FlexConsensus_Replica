"""
FlexConsensus Web App - Analisis interactivo de proteinas
Conectado a RCSB PDB, UniProt y EMDB para buscar proteinas reales
"""
import json
import os
import hashlib
import time
import numpy as np
import requests
from flask import Flask, render_template, jsonify, request

app = Flask(__name__)

# Soporte para correr detrás de Apache reverse proxy en /flexconsensus/
class ReverseProxied:
    def __init__(self, app):
        self.app = app
    def __call__(self, environ, start_response):
        script_name = environ.get('HTTP_X_SCRIPT_NAME', '')
        if script_name:
            environ['SCRIPT_NAME'] = script_name
            path_info = environ['PATH_INFO']
            if path_info.startswith(script_name):
                environ['PATH_INFO'] = path_info[len(script_name):]
        return self.app(environ, start_response)

app.wsgi_app = ReverseProxied(app.wsgi_app)

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
ANALYSES_DIR = os.path.join(os.path.dirname(__file__), "data", "analyses")
os.makedirs(ANALYSES_DIR, exist_ok=True)


# =============================================
# PAGES
# =============================================

@app.route("/")
def index():
    return render_template("app.html")


# =============================================
# API: SEARCH PROTEINS (RCSB PDB)
# =============================================

@app.route("/api/search")
def api_search():
    """Search proteins in RCSB PDB database"""
    q = request.args.get("q", "").strip()
    if len(q) < 2:
        return jsonify({"results": [], "total": 0})

    try:
        # RCSB PDB Search API v2
        search_url = "https://search.rcsb.org/rcsbsearch/v2/query"
        query = {
            "query": {
                "type": "terminal",
                "service": "full_text",
                "parameters": {"value": q}
            },
            "return_type": "entry",
            "request_options": {
                "paginate": {"start": 0, "rows": 20},
                "results_content_type": ["experimental"],
                "sort": [{"sort_by": "score", "direction": "desc"}]
            }
        }

        resp = requests.post(search_url, json=query, timeout=10)
        resp.raise_for_status()
        data = resp.json()

        pdb_ids = [r["identifier"] for r in data.get("result_set", [])]
        total = data.get("total_count", 0)

        # Get details for each PDB ID
        results = []
        if pdb_ids:
            ids_str = ",".join(pdb_ids[:12])
            detail_url = f"https://data.rcsb.org/graphql"
            gql_query = """
            query($ids: [String!]!) {
              entries(entry_ids: $ids) {
                rcsb_id
                struct { title }
                rcsb_entry_info {
                  resolution_combined
                  experimental_method
                  deposited_atom_count
                  molecular_weight
                }
                polymer_entities {
                  rcsb_polymer_entity {
                    pdbx_description
                  }
                  entity_poly {
                    rcsb_sample_sequence_length
                    type
                  }
                }
                rcsb_accession_info {
                  deposit_date
                }
              }
            }
            """
            gql_resp = requests.post(
                detail_url,
                json={"query": gql_query, "variables": {"ids": pdb_ids[:12]}},
                timeout=10
            )
            gql_resp.raise_for_status()
            entries = gql_resp.json().get("data", {}).get("entries", [])

            for entry in entries:
                info = entry.get("rcsb_entry_info", {})
                struct = entry.get("struct", {})
                polymers = entry.get("polymer_entities", [])
                accession = entry.get("rcsb_accession_info", {})

                # Get molecule name from first polymer
                mol_name = ""
                seq_length = 0
                mol_type = ""
                if polymers:
                    poly = polymers[0]
                    rcsb_poly = poly.get("rcsb_polymer_entity", {})
                    entity_poly = poly.get("entity_poly", {})
                    mol_name = rcsb_poly.get("pdbx_description", "")
                    seq_length = entity_poly.get("rcsb_sample_sequence_length", 0)
                    mol_type = entity_poly.get("type", "")

                resolution = info.get("resolution_combined")
                if resolution and isinstance(resolution, list):
                    resolution = resolution[0]

                results.append({
                    "pdb_id": entry["rcsb_id"],
                    "title": struct.get("title", "Sin titulo"),
                    "molecule": mol_name,
                    "method": info.get("experimental_method", ""),
                    "resolution": resolution,
                    "atom_count": info.get("deposited_atom_count", 0),
                    "weight": info.get("molecular_weight", 0),
                    "seq_length": seq_length,
                    "mol_type": mol_type,
                    "date": accession.get("deposit_date", ""),
                })

        return jsonify({"results": results, "total": total})

    except requests.exceptions.RequestException as e:
        return jsonify({"error": f"Error conectando con RCSB PDB: {str(e)}", "results": [], "total": 0})


# =============================================
# API: PROTEIN DETAIL
# =============================================

@app.route("/api/protein/<pdb_id>")
def api_protein(pdb_id):
    """Get detailed info about a specific protein from PDB"""
    pdb_id = pdb_id.upper().strip()
    try:
        url = f"https://data.rcsb.org/rest/v1/core/entry/{pdb_id}"
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        data = resp.json()

        # Get polymer entities
        poly_url = f"https://data.rcsb.org/rest/v1/core/polymer_entity/{pdb_id}/1"
        poly_resp = requests.get(poly_url, timeout=10)
        poly_data = poly_resp.json() if poly_resp.ok else {}

        info = data.get("rcsb_entry_info", {})
        struct = data.get("struct", {})
        cell = data.get("cell", {})
        exptl = data.get("exptl", [{}])[0] if data.get("exptl") else {}

        resolution = info.get("resolution_combined")
        if resolution and isinstance(resolution, list):
            resolution = resolution[0]

        result = {
            "pdb_id": pdb_id,
            "title": struct.get("title", ""),
            "method": info.get("experimental_method", ""),
            "resolution": resolution,
            "atom_count": info.get("deposited_atom_count", 0),
            "weight": info.get("molecular_weight", 0),
            "polymer_count": info.get("polymer_entity_count", 0),
            "molecule": poly_data.get("rcsb_polymer_entity", {}).get("pdbx_description", ""),
            "organism": "",
            "seq_length": 0,
            "image_url": f"https://cdn.rcsb.org/images/structures/{pdb_id.lower()}_assembly-1.jpeg",
            "viewer_url": f"https://www.rcsb.org/3d-view/{pdb_id}",
            "pdb_url": f"https://www.rcsb.org/structure/{pdb_id}",
        }

        # Try to get organism
        src = poly_data.get("rcsb_entity_source_organism", [])
        if src:
            result["organism"] = src[0].get("ncbi_scientific_name", "")

        entity_poly = poly_data.get("entity_poly", {})
        if entity_poly:
            result["seq_length"] = entity_poly.get("rcsb_sample_sequence_length", 0)

        return jsonify(result)

    except requests.exceptions.RequestException as e:
        return jsonify({"error": str(e)}), 500


# =============================================
# API: RUN FLEXCONSENSUS ANALYSIS (SIMULATED)
# =============================================

@app.route("/api/analyze", methods=["POST"])
def api_analyze():
    """
    Run FlexConsensus analysis on a protein.
    Generates realistic simulated data based on protein properties.
    """
    body = request.json or {}
    pdb_id = body.get("pdb_id", "UNKNOWN").upper()
    n_particles = int(body.get("n_particles", 30000))
    n_methods = int(body.get("n_methods", 2))
    latent_dim = int(body.get("latent_dim", 8))

    # Create deterministic seed from PDB ID so same protein = same results
    seed = int(hashlib.md5(pdb_id.encode()).hexdigest()[:8], 16) % (2**31)
    rng = np.random.RandomState(seed)

    # Determine number of conformations based on protein (3-7)
    n_conf = 3 + (seed % 5)  # 3 to 7 conformations

    # Generate conformational centers
    centers = rng.randn(n_conf, 3) * 2.5

    # Weights (non-uniform)
    raw_weights = rng.dirichlet(np.ones(n_conf) * 2)
    weights = np.sort(raw_weights)[::-1]  # Most common first

    # Assign particles to conformations
    labels = rng.choice(n_conf, size=n_particles, p=weights)

    # Generate latent spaces for two methods
    def gen_latent(centers, labels, rng, spread=0.8):
        latent = np.zeros((n_particles, 3))
        for i in range(n_conf):
            mask = labels == i
            n = mask.sum()
            latent[mask] = centers[i] + rng.randn(n, 3) * spread
        return latent

    latent_method1 = gen_latent(centers, labels, rng, spread=0.85)

    # Method 2: rotated + different spread
    rotation = rng.randn(3, 3)
    rotation, _ = np.linalg.qr(rotation)  # Random orthogonal matrix
    centers_rot = centers @ rotation.T
    latent_method2 = gen_latent(centers_rot, labels, rng, spread=0.7)

    # Consensus space
    latent_consensus = gen_latent(centers, labels, rng, spread=0.5)

    # Consensus error
    base_error = rng.exponential(0.35, n_particles)
    for i in range(n_conf):
        mask = labels == i
        dist = np.linalg.norm(latent_consensus[mask] - centers[i], axis=1)
        if dist.max() > 0:
            base_error[mask] *= (0.5 + dist / dist.max())
    consensus_error = (base_error - base_error.min()) / (base_error.max() - base_error.min())

    # Mantel test (simulated)
    mantel_r = round(0.55 + rng.random() * 0.35, 3)  # 0.55-0.90
    mantel_p = round(rng.choice([0.001, 0.002, 0.005]), 4)

    # Subsample for visualization
    n_vis = min(5000, n_particles)
    idx = rng.choice(n_particles, size=n_vis, replace=False)
    idx.sort()

    # Per-conformation metrics
    per_conf = []
    conf_names = ["Estado A", "Estado B", "Estado C", "Estado D",
                  "Estado E", "Estado F", "Estado G"]
    for i in range(n_conf):
        mask = labels == i
        fiable = np.mean(consensus_error[mask] < np.percentile(consensus_error, 20)) * 100
        per_conf.append({
            "id": i,
            "name": conf_names[i],
            "n_particles": int(mask.sum()),
            "percentage": round(float(mask.mean()) * 100, 1),
            "error_mean": round(float(np.mean(consensus_error[mask])), 4),
            "error_std": round(float(np.std(consensus_error[mask])), 4),
            "reliable_pct": round(float(fiable), 1),
        })

    # Error histogram
    hist_counts, hist_edges = np.histogram(consensus_error, bins=50)

    # Filtering comparison
    fiable_mask = consensus_error[idx] < np.percentile(consensus_error, 20)

    # Save analysis
    analysis_id = f"{pdb_id}_{seed}"
    analysis = {
        "id": analysis_id,
        "pdb_id": pdb_id,
        "n_particles": n_particles,
        "n_methods": n_methods,
        "n_conformations": n_conf,
        "latent_dim": latent_dim,
        "mantel_r": mantel_r,
        "mantel_p": mantel_p,
        "per_conformation": per_conf,
        "method1": {
            "name": "CryoDRGN",
            "x": latent_method1[idx, 0].tolist(),
            "y": latent_method1[idx, 1].tolist(),
            "z": latent_method1[idx, 2].tolist(),
        },
        "method2": {
            "name": "HetSIREN",
            "x": latent_method2[idx, 0].tolist(),
            "y": latent_method2[idx, 1].tolist(),
            "z": latent_method2[idx, 2].tolist(),
        },
        "consensus": {
            "x": latent_consensus[idx, 0].tolist(),
            "y": latent_consensus[idx, 1].tolist(),
            "z": latent_consensus[idx, 2].tolist(),
        },
        "labels": labels[idx].tolist(),
        "errors": consensus_error[idx].tolist(),
        "histogram": {
            "counts": hist_counts.tolist(),
            "edges": hist_edges.tolist(),
            "median": round(float(np.median(consensus_error)), 4),
            "p20": round(float(np.percentile(consensus_error, 20)), 4),
            "p80": round(float(np.percentile(consensus_error, 80)), 4),
        },
        "filtering": {
            "all_x": latent_consensus[idx, 0].tolist(),
            "all_y": latent_consensus[idx, 1].tolist(),
            "filtered_x": latent_consensus[idx][fiable_mask, 0].tolist(),
            "filtered_y": latent_consensus[idx][fiable_mask, 1].tolist(),
            "filtered_labels": labels[idx][fiable_mask].tolist(),
            "n_all": int(len(idx)),
            "n_filtered": int(fiable_mask.sum()),
        },
    }

    # Save to disk
    with open(os.path.join(ANALYSES_DIR, f"{analysis_id}.json"), "w") as f:
        json.dump(analysis, f)

    return jsonify(analysis)


@app.route("/api/analysis/<analysis_id>")
def api_get_analysis(analysis_id):
    """Retrieve a saved analysis"""
    path = os.path.join(ANALYSES_DIR, f"{analysis_id}.json")
    if not os.path.exists(path):
        return jsonify({"error": "Analisis no encontrado"}), 404
    with open(path) as f:
        return jsonify(json.load(f))


if __name__ == "__main__":
    app.run(debug=True, port=5000)
