# test_comparison.py
from fastapi import FastAPI, HTTPException
from services.occComparison import compare_models

import os

app = FastAPI()

@app.get("/")
def home():
    return {"message": "Test comparaison OK 🚀"}

@app.post("/compare")
def compare_parts():
    import traceback
    try:
        # Utilisez les fichiers STEP
        ref_path = os.path.abspath("reference_part.step")
        sub_path = os.path.abspath("submitted_part.step")

        if not os.path.exists(ref_path):
            raise HTTPException(status_code=404, detail="Fichier référence introuvable")
        if not os.path.exists(sub_path):
            raise HTTPException(status_code=404, detail="Fichier soumis introuvable")

        result = compare_models(sub_path, ref_path)

        return result

    except HTTPException:
        raise
    except Exception as e:
        tb = traceback.format_exc()
        print(f"[ERROR] Exception in /compare: {e}\n{tb}")
        raise HTTPException(status_code=500, detail=f"Erreur comparaison : {str(e)}")
