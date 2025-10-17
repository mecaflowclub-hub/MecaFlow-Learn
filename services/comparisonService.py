def list_assembly_components(file_path):
    FreeCAD, Part = _import_freecad()
    doc = FreeCAD.newDocument()
    shape = Part.Shape()
    shape.read(file_path)
    components = []
    for solid in shape.Solids:
        com = solid.CenterOfMass
        vol = solid.Volume
        components.append({
            "center_of_mass": tuple(round(float(c), 3) for c in com),
            "volume": round(float(vol), 3)
        })
    FreeCAD.closeDocument(doc.Name)
    return components

def compare_assemblies(submitted_path, reference_path, tol=1e-3):
    sub_comps = list_assembly_components(submitted_path)
    ref_comps = list_assembly_components(reference_path)
    feedback = {}
    # Nombre de sous-pièces
    n_sub = len(sub_comps)
    n_ref = len(ref_comps)
    feedback["num_components"] = {
        "submitted": n_sub,
        "reference": n_ref,
        "ok": n_sub == n_ref,
        "message": "Nombre de sous-pièces correct." if n_sub == n_ref else "Nombre de sous-pièces différent."
    }
    # Correspondance volume/centre de masse (simple, par index)
    matches = []
    for i, (s, r) in enumerate(zip(sub_comps, ref_comps)):
        vol_ok = abs(s["volume"] - r["volume"]) <= tol * max(abs(r["volume"]), 1)
        com_ok = all(abs(sc - rc) <= tol * max(abs(rc), 1) for sc, rc in zip(s["center_of_mass"], r["center_of_mass"]))
        matches.append({
            "index": i,
            "volume_ok": bool(vol_ok),
            "volume_score": 100 - min(100, 100 * abs(s["volume"] - r["volume"]) / (abs(r["volume"]) if abs(r["volume"]) > 1e-6 else 1)),
            "center_of_mass_ok": bool(com_ok),
            "center_of_mass_sub": s["center_of_mass"],
            "center_of_mass_ref": r["center_of_mass"]
        })
    feedback["components_match"] = matches
    # Score global simple
    n_ok = sum(1 for m in matches if m["volume_ok"] and m["center_of_mass_ok"])
    global_score = round(n_ok / max(len(matches), 1) * 100, 1)
    feedback["global_score"] = global_score
    feedback["success"] = global_score >= 80 and n_sub == n_ref
    return feedback
import sys
sys.path.append(r"D:\AURES\Documents\FreeCAD 1.0\bin")
import sys
import importlib
def _import_freecad():
    # Ajoute le chemin de FreeCAD à sys.path si besoin (adapter selon votre installation)
    # Exemple pour Windows :
    # sys.path.append(r'C:\Program Files\FreeCAD 0.20\bin')
    try:
        import FreeCAD
        import FreeCADGui
        import Part
        return FreeCAD, Part
    except ImportError:
        # Si FreeCAD n'est pas dans le PATH, essayez d'ajouter le chemin manuellement ici
        raise ImportError("FreeCAD Python modules not found. Ajoutez le chemin de FreeCAD à sys.path.")

def get_step_properties(file_path):
    print(f"[FreeCAD] Import modules...")
    FreeCAD, Part = _import_freecad()
    print(f"[FreeCAD] New document...")
    doc = FreeCAD.newDocument()
    print(f"[FreeCAD] Create shape...")
    shape = Part.Shape()
    print(f"[FreeCAD] Read STEP file: {file_path}")
    shape.read(file_path)
    print(f"[FreeCAD] Get volume...")
    volume = shape.Volume
    print(f"[FreeCAD] Get bounding box...")
    bbox = shape.BoundBox
    dimensions = (bbox.XLength, bbox.YLength, bbox.ZLength)
    print(f"[FreeCAD] Get topology...")
    faces = shape.Faces
    edges = shape.Edges
    verts = shape.Vertexes
    print(f"[FreeCAD] Get principal moments of inertia...")
    principal_moments = []
    try:
        import numpy as np
        solids = shape.Solids
        if solids:
            # Try to compute moments for each solid and average if possible
            moments_list = []
            for solid in solids:
                try:
                    inertia = solid.MatrixOfInertia
                    moi_matrix = np.array([
                        [inertia.A11, inertia.A12, inertia.A13],
                        [inertia.A21, inertia.A22, inertia.A23],
                        [inertia.A31, inertia.A32, inertia.A33]
                    ])
                    eigvals, _ = np.linalg.eig(moi_matrix)
                    moments_list.append([round(abs(v), 3) for v in eigvals])
                except Exception as solid_err:
                    print(f"[FreeCAD] Erreur sur un solide: {solid_err}")
            if moments_list:
                # Flatten all eigenvalues and take the three largest absolute values
                flat = [abs(v) for sublist in moments_list for v in sublist]
                flat_sorted = sorted(flat, reverse=True)
                if flat_sorted:
                    # Take the three largest, pad with zeros if needed
                    principal_moments = [round(v, 3) for v in flat_sorted[:3]]
                    while len(principal_moments) < 3:
                        principal_moments.append(0.0)
                else:
                    principal_moments = [0.0, 0.0, 0.0]
            else:
                print("[FreeCAD] Aucun moment principal extrait des solides.")
        else:
            print("[FreeCAD] Aucun solide trouvé dans le STEP.")
    except Exception as e:
        print(f"[FreeCAD] Erreur extraction moments principaux : {e}")
        principal_moments = []
    print(f"[FreeCAD] Close document...")
    FreeCAD.closeDocument(doc.Name)
    print(f"[FreeCAD] Done. Returning properties.")
    return {
        "dimensions": tuple(round(float(d), 3) for d in dimensions),
        "volume": round(float(volume), 3),
        "topology": {"faces": len(faces), "edges": len(edges), "vertices": len(verts)},
        "principal_moments": principal_moments,
    }

def compare_step_models(submitted_path, reference_path, tol=1e-3):
    submitted = get_step_properties(submitted_path)
    reference = get_step_properties(reference_path)
    feedback = {}
    score = 0
    total = 0
    # Dimensions
    dims_sub = submitted["dimensions"]
    dims_ref = reference["dimensions"]
    dims_ok = [bool(abs(s - r) <= tol * max(abs(r), 1)) for s, r in zip(dims_sub, dims_ref)]
    dims_pct = [float(100 - min(100, 100 * abs(s - r) / (abs(r) if abs(r) > 1e-6 else 1))) for s, r in zip(dims_sub, dims_ref)]
    dims_score = float(sum(dims_pct)) / len(dims_pct) if dims_pct else 0.0
    score += dims_score
    total += 100
    if all(dims_ok):
        feedback["dimensions"] = {"ok": True, "score": float(dims_score), "pct": [float(p) for p in dims_pct], "message": "Dimensions correctes."}
    else:
        feedback["dimensions"] = {"ok": False, "score": float(dims_score), "pct": [float(p) for p in dims_pct], "message": "Erreur sur les dimensions : vérifiez la taille ou l'unité du modèle."}

    # Volume
    vol_sub = submitted["volume"]
    vol_ref = reference["volume"]
    vol_ok = bool(abs(vol_sub - vol_ref) <= tol * max(abs(vol_ref), 1))
    vol_pct = float(100 - min(100, 100 * abs(vol_sub - vol_ref) / (abs(vol_ref) if abs(vol_ref) > 1e-6 else 1)))
    vol_score = vol_pct
    score += vol_score
    total += 100
    if vol_ok:
        feedback["volume"] = {"ok": True, "score": vol_score, "message": "Volume correct."}
    else:
        feedback["volume"] = {"ok": False, "score": vol_score, "message": "Erreur sur le volume : vérifiez l'épaisseur ou la géométrie du modèle."}

    # Moments principaux
    pm_sub = submitted.get("principal_moments", [])
    pm_ref = reference.get("principal_moments", [])
    shell_only = False
    # Detect if either file is shell-only (no solids)
    if (not pm_sub or pm_sub == [0.0, 0.0, 0.0]) or (not pm_ref or pm_ref == [0.0, 0.0, 0.0]):
        shell_only = True
    if shell_only:
        feedback["principal_moments"] = {"ok": None, "score": 0.0, "message": "Le modèle contient uniquement des surfaces/coques, le calcul des moments principaux n'est pas possible, mais le reste de la vérification est effectué."}
    elif pm_sub and pm_ref and len(pm_sub) == len(pm_ref):
        pm_ok = [bool(abs(s - r) <= tol * max(abs(r), 1)) for s, r in zip(pm_sub, pm_ref)]
        pm_pct = [float(100 - min(100, 100 * abs(s - r) / (abs(r) if abs(r) > 1e-6 else 1))) for s, r in zip(pm_sub, pm_ref)]
        pm_score = float(sum(pm_pct)) / len(pm_pct) if pm_pct else 0.0
        score += pm_score
        total += 100
        if all(pm_ok):
            feedback["principal_moments"] = {"ok": True, "score": float(pm_score), "pct": [float(p) for p in pm_pct], "message": "Moments d'inertie principaux corrects."}
        else:
            feedback["principal_moments"] = {"ok": False, "score": float(pm_score), "pct": [float(p) for p in pm_pct], "message": "Erreur sur les moments principaux : vérifiez la répartition de la matière ou la symétrie."}
    else:
        feedback["principal_moments"] = {"ok": None, "score": 0.0, "message": "Moments principaux non calculés."}

    # Topologie
    topo_sub = submitted["topology"]
    topo_ref = reference["topology"]
    topo_ok = bool(topo_sub == topo_ref)
    topo_score = 100.0 if topo_ok else 0.0
    score += topo_score
    total += 100
    if topo_ok:
        feedback["topology"] = {"ok": True, "score": topo_score, "message": "Topologie correcte."}
    else:
        feedback["topology"] = {"ok": False, "score": topo_score, "message": "Erreur sur la topologie : vérifiez le nombre de faces, arêtes ou sommets."}

    # Score global
    global_score = round(float(score) / float(total) * 100, 1)
    feedback["global_score"] = global_score
    feedback["success"] = bool(global_score >= 80)  # Seuil de réussite paramétrable

    return {
        "submitted": submitted,
        "reference": reference,
        "feedback": feedback
    }



