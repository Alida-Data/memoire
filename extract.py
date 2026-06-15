import os
import requests
import zipfile
import shutil
from fastapi import FastAPI, HTTPException
import uvicorn

class KaggleExtractor:
    """Classe responsable de l'extraction de datasets via l'API REST de Kaggle."""
    
    def __init__(self, username: str, api_key: str, dataset_url: str, output_dir: str = "/data", filename: str = "raw_data.csv"):
        self.username = username
        self.api_key = api_key
        self.dataset_url = dataset_url
        self.output_dir = output_dir
        self.destination_file = os.path.join(self.output_dir, filename)
        self.zip_path = os.path.join(self.output_dir, "dataset.zip")

    def _prepare_directory(self):
        """Méthode interne pour s'assurer que le dossier de stockage existe."""
        os.makedirs(self.output_dir, exist_ok=True)

    def download_zip(self):
        """Gère l'authentification et le téléchargement du fichier compressé par morceaux."""
        print(f"[INFO] Connexion à l'API Kaggle et téléchargement du dataset...")
        response = requests.get(self.dataset_url, auth=(self.username, self.api_key), stream=True)
        
        if response.status_code == 401:
            raise HTTPException(status_code=401, detail="Échec d'authentification : Vérifie ton Username ou ta Clé API Kaggle.")
        elif response.status_code != 200:
            raise HTTPException(status_code=response.status_code, detail=f"Erreur de téléchargement Kaggle (Code: {response.status_code})")
            
        with open(self.zip_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
        print("[INFO] Archive .zip reçue avec succès.")

    def extract_csv(self):
        """Extrait le premier fichier CSV identifié dans l'archive téléchargée."""
        print("[INFO] Extraction du fichier CSV...")
        with zipfile.ZipFile(self.zip_path, 'r') as zip_ref:
            csv_files = [f for f in zip_ref.namelist() if f.endswith('.csv')]
            if not csv_files:
                raise HTTPException(status_code=404, detail="Aucun fichier CSV trouvé à l'intérieur du ZIP téléchargé.")
            
            source_csv = csv_files[0]
            with zip_ref.open(source_csv) as source, open(self.destination_file, 'wb') as target:
                shutil.copyfileobj(source, target)

    def clean_temporary_files(self):
        """Supprime les résidus du téléchargement (.zip)."""
        if os.path.exists(self.zip_path):
            os.remove(self.zip_path)

    def run_pipeline(self) -> str:
        """Orchestre la totalité du processus d'extraction."""
        self._prepare_directory()
        try:
            self.download_zip()
            self.extract_csv()
            print(f"[SUCCESS] Données extraites et déplacées dans : {self.destination_file}")
            return self.destination_file
        finally:
            self.clean_temporary_files()


# =====================================================================
# Configuration et initialisation du microservice FastAPI
# =====================================================================

app = FastAPI(title="Extract Microservice")

# Vos identifiants et configuration réels de production
KAGGLE_USER = "sopiealidandin"
KAGGLE_KEY = "KGAT_126cf48b86c24cb9f22c64b91b49c054"
DATASET_API_URL = "https://www.kaggle.com/api/v1/datasets/download/ismetsemedov/transactions"

# Instance unique configurée pour l'environnement Docker
extractor = KaggleExtractor(
    username=KAGGLE_USER,
    api_key=KAGGLE_KEY,
    dataset_url=DATASET_API_URL,
    output_dir="/data",          # Volume partagé Docker
    filename="raw_data.csv"
)

@app.post("/run")
def extract():
    try:
        saved_path = extractor.run_pipeline()
        return {
            "status": "success",
            "message": "Extraction HTTP directe en POO réussie !",
            "path": saved_path
        }
    except HTTPException as http_e:
        raise http_e
    except Exception as e:
        print(f"[ERROR] Échec critique du microservice d'extraction : {str(e)}")
        raise HTTPException(status_code=500, detail=f"Erreur interne d'extraction : {str(e)}")


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)