import os
import subprocess
import json

def compare_dxf_drawings(submitted_path, reference_path, tol=1e-3):
    # Import FreeCAD and importDXF only inside this function
    import FreeCAD
    import importDXF

    # Charger les deux DXF dans FreeCAD
    doc_ref = FreeCAD.newDocument("Reference")
    importDXF.open(reference_path)
    doc_sub = FreeCAD.newDocument("Submitted")
    importDXF.open(submitted_path)

    # Récupérer les entités (lignes, arcs, polylignes)
    def get_entities(doc):
        return [obj for obj in doc.Objects if hasattr(obj, "Shape")]

    ref_entities = get_entities(doc_ref)
    sub_entities = get_entities(doc_sub)

    # Comparer les bounding boxes
    matched = 0
    for ref in ref_entities:
        for sub in sub_entities:
            if ref.Shape.BoundBox.isEqual(sub.Shape.BoundBox, tol):
                matched += 1
                break

    # Nettoyer les documents
    FreeCAD.closeDocument(doc_ref.Name)
    FreeCAD.closeDocument(doc_sub.Name)

    # Résultat
    result = {
        "success": True,
        "matched": matched,
        "total_reference": len(ref_entities),
        "total_submitted": len(sub_entities),
        "score": round(100 * matched / max(len(ref_entities), 1), 2),
        "message": "Comparaison DXF terminée."
    }
    return result


def compare_dxf_external(submitted_path, reference_path):
    """Call worker script in a subprocess and parse its JSON output safely."""
    try:
        result = subprocess.run(
            [
                "D:/AURES/Documents/FreeCAD 1.0/bin/python.exe",
                "services/compare_dxf_worker.py",
                reference_path,
                submitted_path,
            ],
            capture_output=True,
            text=True,
            timeout=60
        )

        stdout = result.stdout.strip()
        stderr = result.stderr.strip()

        if not stdout:
            return {
                "success": False,
                "error": "Worker returned empty output",
                "stderr": stderr,
            }

        try:
            return json.loads(stdout)
        except json.JSONDecodeError as e:
            return {
                "success": False,
                "error": f"Invalid JSON output: {e}",
                "stdout": stdout,
                "stderr": stderr,
            }

    except Exception as e:
        return {"success": False, "error": str(e)}
