import os
import ezdxf
from ezdxf.lldxf.const import DXFError
from OCC.Core.BRepBuilderAPI import (
    BRepBuilderAPI_MakeEdge, BRepBuilderAPI_MakeWire,
    BRepBuilderAPI_MakeFace
)
from OCC.Core.gp import gp_Pnt, gp_Circ, gp_Ax2, gp_Dir, gp_Vec, gp_Pln
from OCC.Core.GC import GC_MakeArcOfCircle
from OCC.Core.BRep import BRep_Tool
from OCC.Core.TopAbs import TopAbs_EDGE
from OCC.Core.TopExp import TopExp_Explorer
from OCC.Core.TopoDS import topods
from OCC.Core.BRepBndLib import brepbndlib
from OCC.Core.Bnd import Bnd_Box
import math
import json

def analyze_dxf(path):
    """Analyze DXF entities and return counts by type."""
    if not os.path.exists(path):
        raise FileNotFoundError(f"Le fichier DXF n'existe pas: {path}")
        
    try:
        doc = ezdxf.readfile(path)
    except ezdxf.DXFError as e:
        raise ValueError(f"Erreur lors de la lecture du fichier DXF: {e}")
        
    msp = doc.modelspace()

    counts = {
        "LINE": 0,
        "CIRCLE": 0,
        "ARC": 0,
        "POLYLINE": 0,
        "LWPOLYLINE": 0,
        "DIMENSION": 0,
        "TEXT": 0,
        "MTEXT": 0,
    }
    
    geometries = {
        "LINES": [],
        "CIRCLES": [],
        "ARCS": [],
        "POLYLINES": []
    }

    for entity in msp:
        etype = entity.dxftype()
        if etype in counts:
            counts[etype] += 1

        # Extract geometry data
        if etype == "LINE":
            start = entity.dxf.start
            end = entity.dxf.end
            geometries["LINES"].append({
                "start": (start[0], start[1], start[2] if len(start) > 2 else 0),
                "end": (end[0], end[1], end[2] if len(end) > 2 else 0)
            })
        elif etype == "CIRCLE":
            center = entity.dxf.center
            geometries["CIRCLES"].append({
                "center": (center[0], center[1], center[2] if len(center) > 2 else 0),
                "radius": entity.dxf.radius
            })
        elif etype == "ARC":
            center = entity.dxf.center
            geometries["ARCS"].append({
                "center": (center[0], center[1], center[2] if len(center) > 2 else 0),
                "radius": entity.dxf.radius,
                "start_angle": entity.dxf.start_angle,
                "end_angle": entity.dxf.end_angle
            })
        elif etype in ["POLYLINE", "LWPOLYLINE"]:
            points = []
            if etype == "LWPOLYLINE":
                for vertex in entity:
                    points.append((vertex[0], vertex[1], 0))
            else:
                for vertex in entity.vertices:
                    loc = vertex.dxf.location
                    points.append((loc[0], loc[1], loc[2] if len(loc) > 2 else 0))
            geometries["POLYLINES"].append(points)

    return counts, geometries

def create_occ_geometry(geometries):
    """Convert DXF geometry data to OpenCascade shapes."""
    shapes = []
    
    # Create lines
    for line in geometries["LINES"]:
        start = gp_Pnt(*line["start"])
        end = gp_Pnt(*line["end"])
        edge = BRepBuilderAPI_MakeEdge(start, end).Edge()
        shapes.append(edge)
    
    # Create circles
    for circle in geometries["CIRCLES"]:
        center = gp_Pnt(*circle["center"])
        axis = gp_Ax2(center, gp_Dir(0, 0, 1))
        circ = gp_Circ(axis, circle["radius"])
        edge = BRepBuilderAPI_MakeEdge(circ).Edge()
        shapes.append(edge)
    
    # Create arcs
    for arc in geometries["ARCS"]:
        center = gp_Pnt(*arc["center"])
        radius = arc["radius"]
        start_angle = math.radians(arc["start_angle"])
        end_angle = math.radians(arc["end_angle"])
        
        # Calculate points on arc
        start_point = gp_Pnt(
            center.X() + radius * math.cos(start_angle),
            center.Y() + radius * math.sin(start_angle),
            center.Z()
        )
        end_point = gp_Pnt(
            center.X() + radius * math.cos(end_angle),
            center.Y() + radius * math.sin(end_angle),
            center.Z()
        )
        
        # Calculate middle point
        mid_angle = (start_angle + end_angle) / 2
        mid_point = gp_Pnt(
            center.X() + radius * math.cos(mid_angle),
            center.Y() + radius * math.sin(mid_angle),
            center.Z()
        )
        
        arc = GC_MakeArcOfCircle(start_point, mid_point, end_point).Value()
        edge = BRepBuilderAPI_MakeEdge(arc).Edge()
        shapes.append(edge)
    
    # Create polylines
    for polyline in geometries["POLYLINES"]:
        if len(polyline) < 2:
            continue
            
        wire_builder = BRepBuilderAPI_MakeWire()
        for i in range(len(polyline) - 1):
            start = gp_Pnt(*polyline[i])
            end = gp_Pnt(*polyline[i + 1])
            edge = BRepBuilderAPI_MakeEdge(start, end).Edge()
            wire_builder.Add(edge)
        
        if wire_builder.IsDone():
            shapes.append(wire_builder.Wire())
    
    return shapes

def compare_geometry(shape1, shape2, tolerance=1e-3):
    """Compare two OpenCascade shapes for similarity."""
    # Compare bounding boxes
    bbox1 = Bnd_Box()
    bbox2 = Bnd_Box()
    brepbndlib.Add(shape1, bbox1)
    brepbndlib.Add(shape2, bbox2)
    
    # Compare dimensions
    if (abs(bbox1.CornerMin().X() - bbox2.CornerMin().X()) > tolerance or
        abs(bbox1.CornerMin().Y() - bbox2.CornerMin().Y()) > tolerance or
        abs(bbox1.CornerMax().X() - bbox2.CornerMax().X()) > tolerance or
        abs(bbox1.CornerMax().Y() - bbox2.CornerMax().Y()) > tolerance):
        return False
    
    # Compare edges
    exp1 = TopExp_Explorer(shape1, TopAbs_EDGE)
    exp2 = TopExp_Explorer(shape2, TopAbs_EDGE)
    
    edges1 = []
    edges2 = []
    
    while exp1.More():
        edge = topods.Edge(exp1.Current())
        curve, start, end = BRep_Tool().Curve(edge)
        edges1.append((curve, start, end))
        exp1.Next()
    
    while exp2.More():
        edge = topods.Edge(exp2.Current())
        curve, start, end = BRep_Tool().Curve(edge)
        edges2.append((curve, start, end))
        exp2.Next()
    
    return len(edges1) == len(edges2)

def compare_dxf_drawings(submitted_path, reference_path, tol=1e-3):
    """Compare two DXF files using OpenCascade and ezdxf."""
    try:
        # First check if both files exist
        if not os.path.exists(reference_path):
            return {
                "success": False,
                "error": "Fichier de référence introuvable",
                "message": f"Le fichier de référence n'existe pas: {reference_path}"
            }
            
        if not os.path.exists(submitted_path):
            return {
                "success": False,
                "error": "Fichier soumis introuvable",
                "message": f"Le fichier soumis n'existe pas: {submitted_path}"
            }

        # Try to analyze both files
        try:
            ref_counts, ref_geom = analyze_dxf(reference_path)
        except Exception as e:
            return {
                "success": False,
                "error": "Erreur de lecture du fichier de référence",
                "message": str(e)
            }

        try:
            sub_counts, sub_geom = analyze_dxf(submitted_path)
        except Exception as e:
            return {
                "success": False,
                "error": "Erreur de lecture du fichier soumis",
                "message": str(e)
            }
        
        # Create OpenCascade geometry
        ref_shapes = create_occ_geometry(ref_geom)
        sub_shapes = create_occ_geometry(sub_geom)
        
        # Compare geometry
        matched_shapes = 0
        for ref_shape in ref_shapes:
            for sub_shape in sub_shapes:
                if compare_geometry(ref_shape, sub_shape, tol):
                    matched_shapes += 1
                    break
        
        # Calculate score
        total_ref_shapes = len(ref_shapes)
        total_sub_shapes = len(sub_shapes)
        
        if total_ref_shapes == 0:
            score = 0
        else:
            score = round((matched_shapes / total_ref_shapes) * 100, 2)
        
        # Compare entity counts
        counts_match = {
            key: ref_counts[key] == sub_counts[key]
            for key in ref_counts.keys()
        }
        
        return {
            "success": True,
            "matched_shapes": matched_shapes,
            "total_reference": total_ref_shapes,
            "total_submitted": total_sub_shapes,
            "score": score,
            "message": "DXF comparison complete",
            "entity_counts": {
                "reference": ref_counts,
                "submitted": sub_counts,
                "matches": counts_match
            }
        }
        
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "message": "Error during DXF comparison"
        }