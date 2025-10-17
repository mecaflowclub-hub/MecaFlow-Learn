import sys
import json
import ezdxf

def analyze_dxf(path):
    """Analyze DXF entities and return counts by type."""
    doc = ezdxf.readfile(path)
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

    for e in msp:
        etype = e.dxftype()
        if etype in counts:
            counts[etype] += 1

    return counts

def compare_dxf(reference_path, submitted_path):
    """Compare two DXF files and return structured JSON results."""
    ref_counts = analyze_dxf(reference_path)
    sub_counts = analyze_dxf(submitted_path)

    results = {}
    for key in ref_counts.keys():
        results[key if key != "DIMENSION" else "DIMENSIONS"] = (
            ref_counts[key] == sub_counts[key]
        )

    # Compute score: number of entity types that match
    total_types = len(results)
    matched_types = sum(1 for v in results.values() if v)
    score = round((matched_types / total_types) * 100, 2) if total_types else 0

    return {
        "success": True,
        "message": "DXF comparison complete.",
        "results": results,
        "counts": {
            "reference": ref_counts,
            "submitted": sub_counts,
            "ref_dimensions": ref_counts.get("DIMENSION", 0),
            "sub_dimensions": sub_counts.get("DIMENSION", 0),
        },
        "score": score,
    }

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(json.dumps({
            "success": False,
            "message": "Usage: compare_dxf_worker.py reference.dxf submitted.dxf"
        }))
        sys.exit(1)

    reference_path = sys.argv[1]
    submitted_path = sys.argv[2]

    result = compare_dxf(reference_path, submitted_path)
    print(json.dumps(result))
