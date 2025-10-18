from typing import Dict, List, Any, Tuple
from OCC.Core.STEPControl import STEPControl_Reader
from OCC.Core.BRepGProp import brepgprop_VolumeProperties, brepgprop_SurfaceProperties
from OCC.Core.GProp import GProp_GProps
from OCC.Core.TopAbs import TopAbs_FACE, TopAbs_EDGE, TopAbs_VERTEX, TopAbs_SOLID, TopAbs_SHELL
from OCC.Core.TopExp import TopExp_Explorer
from OCC.Core.TopoDS import topods, TopoDS_Shape
from OCC.Core.BRepBndLib import brepbndlib
from OCC.Core.Bnd import Bnd_Box
import numpy as np

# -------------------------------
# STEP file utilities
# -------------------------------

def read_step_file(filename: str) -> TopoDS_Shape:
    reader = STEPControl_Reader()
    status = reader.ReadFile(filename)
    if status != 1:  # IFSelect_RetDone
        raise Exception(f"Error reading STEP file: {filename}")
    reader.TransferRoots()
    return reader.OneShape()

def get_solids_from_shape(shape: TopoDS_Shape):
    solids = []
    exp = TopExp_Explorer(shape, TopAbs_SOLID)
    while exp.More():
        solids.append(topods.Solid(exp.Current()))
        exp.Next()
    return solids

def get_shells_from_shape(shape: TopoDS_Shape):
    shells = []
    exp = TopExp_Explorer(shape, TopAbs_SHELL)
    while exp.More():
        shells.append(topods.Shell(exp.Current()))
        exp.Next()
    return shells

def get_faces_from_shape(shape: TopoDS_Shape):
    faces = []
    exp = TopExp_Explorer(shape, TopAbs_FACE)
    while exp.More():
        faces.append(topods.Face(exp.Current()))
        exp.Next()
    return faces

# -------------------------------
# Property extraction
# -------------------------------

def count_subshapes(shape: TopoDS_Shape, subshape_type):
    count = 0
    explorer = TopExp_Explorer(shape, subshape_type)
    while explorer.More():
        count += 1
        explorer.Next()
    return count

def get_solid_properties(solid: TopoDS_Shape):
    props = GProp_GProps()
    brepgprop_VolumeProperties(solid, props)

    volume = props.Mass()
    com = props.CentreOfMass()

    # Bounding box
    bbox = Bnd_Box()
    brepbndlib.Add(solid, bbox)
    xmin, ymin, zmin, xmax, ymax, zmax = bbox.Get()
    dimensions = (xmax - xmin, ymax - ymin, zmax - zmin)

    # Topology
    # Count faces
    face_explorer = TopExp_Explorer(solid, TopAbs_FACE)
    num_faces = 0
    while face_explorer.More():
        num_faces += 1
        face_explorer.Next()

    # Count edges
    edge_explorer = TopExp_Explorer(solid, TopAbs_EDGE)
    num_edges = 0
    while edge_explorer.More():
        num_edges += 1
        edge_explorer.Next()

    # Count vertices
    vertex_explorer = TopExp_Explorer(solid, TopAbs_VERTEX)
    num_vertices = 0
    while vertex_explorer.More():
        num_vertices += 1
        vertex_explorer.Next()

    # Principal moments
    matrix = props.MatrixOfInertia()
    moi_matrix = np.array([[matrix.Value(i, j) for j in range(1, 4)] for i in range(1, 4)])
    eigvals = np.linalg.eigvals(moi_matrix)

    return {
        "volume": round(float(volume), 3),
        "center_of_mass": (
            round(float(com.X()), 3),
            round(float(com.Y()), 3),
            round(float(com.Z()), 3)
        ),
        "dimensions": tuple(round(float(d), 3) for d in dimensions),
        "topology": {"faces": num_faces, "edges": num_edges, "vertices": num_vertices},
        "principal_moments": [round(float(abs(v)), 3) for v in eigvals]
    }

def get_shell_properties(shell: TopoDS_Shape):
    props = GProp_GProps()
    brepgprop_SurfaceProperties(shell, props)
    
    # Bounding box
    bbox = Bnd_Box()
    brepbndlib.Add(shell, bbox)
    xmin, ymin, zmin, xmax, ymax, zmax = bbox.Get()
    dimensions = (xmax - xmin, ymax - ymin, zmax - zmin)
    
    # Topology
    num_faces = count_subshapes(shell, TopAbs_FACE)
    num_edges = count_subshapes(shell, TopAbs_EDGE)
    num_vertices = count_subshapes(shell, TopAbs_VERTEX)
    
    # Get principal properties
    principal_props = props.MatrixOfInertia()
    
    return {
        "surface_area": round(float(props.Mass()), 3),
        "center_of_mass": (
            round(float(props.CentreOfMass().X()), 3),
            round(float(props.CentreOfMass().Y()), 3),
            round(float(props.CentreOfMass().Z()), 3)
        ),
        "dimensions": tuple(round(float(d), 3) for d in dimensions),
        "topology": {"faces": num_faces, "edges": num_edges, "vertices": num_vertices},
        "type": "shell" if num_faces > 1 else "surface",
        "principal_moments": (
            round(float(principal_props.Value(1, 1)), 3),
            round(float(principal_props.Value(2, 2)), 3),
            round(float(principal_props.Value(3, 3)), 3)
        )
    }

def get_face_properties(face: TopoDS_Shape):
    return get_shell_properties(face)  # Même logique peut être utilisée

def get_shape_properties(shape: TopoDS_Shape):
    """Global properties for models (solids, shells, or surfaces)"""
    if not shape:
        raise ValueError("Invalid shape: None")

    solids = get_solids_from_shape(shape)
    if solids:
        return get_solid_properties(solids[0])
    
    shells = get_shells_from_shape(shape)
    if shells:
        if len(shells) == 1:
            return get_shell_properties(shells[0])
        else:
            # Process multiple shells
            total_area = 0.0
            total_faces = 0
            total_edges = 0
            total_vertices = 0
            bbox = Bnd_Box()
            for shell in shells:
                brepbndlib.Add(shell, bbox)
            xmin, ymin, zmin, xmax, ymax, zmax = bbox.Get()
            dimensions = (xmax - xmin, ymax - ymin, zmax - zmin)
            
            # Calculate combined properties
            props = GProp_GProps()
            for shell in shells:
                brepgprop_SurfaceProperties(shell, props)
                total_area += float(props.Mass())
                total_faces += count_subshapes(shell, TopAbs_FACE)
                total_edges += count_subshapes(shell, TopAbs_EDGE)
                total_vertices += count_subshapes(shell, TopAbs_VERTEX)
            
            return {
                "surface_area": round(total_area, 3),
                "center_of_mass": (
                    round(float(props.CentreOfMass().X()), 3),
                    round(float(props.CentreOfMass().Y()), 3),
                    round(float(props.CentreOfMass().Z()), 3)
                ),
                "dimensions": tuple(round(float(d), 3) for d in dimensions),
                "topology": {"faces": total_faces, "edges": total_edges, "vertices": total_vertices},
                "type": "shell",
                "principal_moments": (
                    round(float(total_area), 3),
                    round(float(total_area), 3),
                    round(float(total_area), 3)
                )
            }
    
    # Enfin essayer les faces
    faces = get_faces_from_shape(shape)
    if faces:
        return get_face_properties(faces[0])
        
    raise ValueError("No valid geometry (solid, shell, or face) found in shape.")

# -------------------------------
# Comparison
# -------------------------------

def compare_models(submitted_path: str, reference_path: str, tol: float = 1e-3) -> Dict[str, Any]:
    """Compare two STEP models (can handle both single parts and assemblies).
    
    Args:
        submitted_path: Path to the submitted STEP file
        reference_path: Path to the reference STEP file
        tol: Tolerance for comparisons (default: 1e-3, use higher values like 1e-2 or 5e-2 for less strict comparison)
    """
    sub_shape = read_step_file(submitted_path)
    ref_shape = read_step_file(reference_path)

    sub_solids = get_solids_from_shape(sub_shape)
    ref_solids = get_solids_from_shape(ref_shape)

    # Initialize feedback dictionary with proper type hints
    feedback: Dict[str, Any] = {}

    # -----------------
    # Assembly mode
    # -----------------
    if len(ref_solids) > 1 or len(sub_solids) > 1:
        feedback = {
            "num_components": {
                "submitted": len(sub_solids),
                "reference": len(ref_solids),
                "ok": len(sub_solids) == len(ref_solids),
                "message": "Nombre de sous-pièces correct." if len(sub_solids) == len(ref_solids)
                           else "Nombre de sous-pièces différent."
            }
        }

        matches = []
        for i, (sub_solid, ref_solid) in enumerate(zip(sub_solids, ref_solids)):
            sub_props = get_solid_properties(sub_solid)
            ref_props = get_solid_properties(ref_solid)

            vol_ok = abs(sub_props["volume"] - ref_props["volume"]) <= tol * max(abs(ref_props["volume"]), 1)
            com_ok = all(abs(s - r) <= tol * max(abs(r), 1)
                         for s, r in zip(sub_props["center_of_mass"], ref_props["center_of_mass"]))
            topo_ok = sub_props["topology"] == ref_props["topology"]

            vol_score = 100 - min(100, 100 * abs(sub_props["volume"] - ref_props["volume"]) /
                                  (abs(ref_props["volume"]) if abs(ref_props["volume"]) > 1e-6 else 1))

            matches.append({
                "index": i,
                "volume_ok": bool(vol_ok),
                "volume_score": round(float(vol_score), 1),
                "center_of_mass_ok": bool(com_ok),
                "center_of_mass_sub": sub_props["center_of_mass"],
                "center_of_mass_ref": ref_props["center_of_mass"],
                "topology_match": bool(topo_ok)
            })

        feedback["components_match"] = matches
        n_ok = sum(1 for m in matches if m["volume_ok"] and m["center_of_mass_ok"] and m["topology_match"])
        global_score = round(n_ok / max(len(matches), 1) * 100, 1)

        feedback["global_score"] = global_score
        feedback["success"] = global_score >= 80 and len(sub_solids) == len(ref_solids)
        return feedback

    # -----------------
    # Part mode
    # -----------------
    else:
        sub_props = get_shape_properties(sub_shape)
        ref_props = get_shape_properties(ref_shape)

        feedback = {}
        score = 0
        total = 0

        # Dimensions
        dims_ok = [abs(s - r) <= tol * max(abs(r), 1)
                   for s, r in zip(sub_props["dimensions"], ref_props["dimensions"])]
        dims_pct = [100 - min(100, 100 * abs(s - r) / (abs(r) if abs(r) > 1e-6 else 1))
                    for s, r in zip(sub_props["dimensions"], ref_props["dimensions"])]
        dims_score = sum(dims_pct) / len(dims_pct)
        feedback["dimensions"] = {"ok": all(dims_ok), "score": dims_score}
        score += dims_score
        total += 1

        # Volume or Surface Area
        if "volume" in sub_props and "volume" in ref_props:
            # For solids
            measure_ok = abs(sub_props["volume"] - ref_props["volume"]) <= tol * max(abs(ref_props["volume"]), 1)
            measure_score = 100 - min(100, 100 * abs(sub_props["volume"] - ref_props["volume"]) /
                                  (abs(ref_props["volume"]) if abs(ref_props["volume"]) > 1e-6 else 1))
            feedback["volume"] = {"ok": measure_ok, "score": measure_score}
        else:
            # For shells and surfaces
            shell_tol = tol * 1.5  # More tolerant for shells
            area_diff = abs(sub_props["surface_area"] - ref_props["surface_area"])
            measure_ok = area_diff <= shell_tol * max(abs(ref_props["surface_area"]), 1)
            measure_score = 100 - min(100, 100 * area_diff /
                                  (abs(ref_props["surface_area"]) if abs(ref_props["surface_area"]) > 1e-6 else 1))
            
            # Be more lenient with topology for shells
            topo_diff = sum(abs(sub_props["topology"][k] - ref_props["topology"][k]) 
                          for k in ["faces", "edges", "vertices"])
            if topo_diff <= 6:  # Allow some topology differences
                measure_score = min(100, measure_score * 1.1)  # Give bonus for close topology
                
            feedback["surface_area"] = {"ok": measure_ok, "score": round(measure_score, 1)}
        
        score += measure_score
        total += 1

        # Topology
        topo_ok = sub_props["topology"] == ref_props["topology"]
        topo_score = 100 if topo_ok else 0
        feedback["topology"] = {"ok": topo_ok, "score": topo_score}
        score += topo_score
        total += 1

        # Moments of inertia
        pm_ok = all(abs(s - r) <= tol * max(abs(r), 1)
                    for s, r in zip(sub_props["principal_moments"], ref_props["principal_moments"]))
        pm_score = 100 if pm_ok else 0
        feedback["principal_moments"] = {"ok": pm_ok, "score": pm_score}
        score += pm_score
        total += 1

        # Calculate global score (average of all scores)
        global_score = round(score / total, 1)
        feedback["global_score"] = global_score

        # Success threshold varies based on tolerance
        if tol >= 5e-2:  # Very lenient comparison (for mixed solid/shell)
            feedback["success"] = global_score >= 70
        elif tol >= 1e-2:  # Moderately lenient comparison
            feedback["success"] = global_score >= 75
        else:  # Standard strict comparison
            feedback["success"] = global_score >= 80

        return feedback
