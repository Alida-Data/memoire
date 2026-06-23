import os
import hashlib
import pandas as pd
import mlflow
import mlflow.sklearn
import traceback
from fastapi import FastAPI, HTTPException
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score
import uvicorn

class DataTransformer:
    def __init__(self, raw_path: str, cleaned_path: str, chunk_size: int = 50000):
        self.raw_path = raw_path
        self.cleaned_path = cleaned_path
        self.chunk_size = chunk_size

    def _anonymize_card(self, card_number) -> str:
        if pd.notnull(card_number):
            return hashlib.sha256(str(card_number).encode()).hexdigest()
        return None

    def clean_chunk(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        df = df.drop_duplicates()
        
        # 💡 Correction ici : 'is_fraud' au lieu de 'Is Fraud'
        if 'is_fraud' in df.columns:
            df = df.dropna(subset=['is_fraud'])
            def convert_fraud_val(val):
                if pd.isnull(val):
                    return None
                v_str = str(val).strip().lower()
                if v_str in ['yes', '1', '1.0', 'true']:
                    return 1
                if v_str in ['no', '0', '0.0', 'false']:
                    return 0
                return None
            df['is_fraud'] = df['is_fraud'].apply(convert_fraud_val)
            df = df.dropna(subset=['is_fraud'])
            if not df.empty:
                df['is_fraud'] = df['is_fraud'].astype(int)
                
        # 💡 Correction ici : 'card_number' au lieu de 'Credit Card Number'
        if 'card_number' in df.columns:
            df['card_number'] = df['card_number'].apply(self._anonymize_card)
        return df

    def run_pipeline(self) -> str:
        if not os.path.exists(self.raw_path):
            raise FileNotFoundError(f"Fichier brut {self.raw_path} introuvable.")
            
        if os.path.exists(self.cleaned_path):
            os.remove(self.cleaned_path)
            
        is_first_chunk = True
        for chunk in pd.read_csv(self.raw_path, chunksize=self.chunk_size):
            cleaned_chunk = self.clean_chunk(chunk)
            if not cleaned_chunk.empty:
                cleaned_chunk.to_csv(self.cleaned_path, mode='a', index=False, header=is_first_chunk)
                is_first_chunk = False
        return self.cleaned_path

class ModelTrainer:
    # 💡 Correction ici : cible par défaut fixée à 'is_fraud'
    def __init__(self, data_path: str, target: str = "is_fraud"):
        self.data_path = data_path
        self.target = target
        self.model = RandomForestClassifier(n_estimators=100, max_depth=10, random_state=42)

    def train(self):
        df = pd.read_csv(self.data_path, nrows=20000)
        
        if self.target not in df.columns:
            raise KeyError(f"La colonne cible '{self.target}' est absente du fichier nettoyé.")
        
        # Enlever les colonnes non numériques + la cible pour l'entraînement
        X = df.select_dtypes(include=['number']).drop(columns=[self.target], errors='ignore')
        y = df[self.target].astype(int)
        
        if X.empty:
            raise ValueError("Le dataset X ne contient aucune colonne numérique exploitable pour l'entraînement.")
        
        X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42, stratify=y)
        self.model.fit(X_train, y_train)
        return accuracy_score(y_test, self.model.predict(X_test))

    def log_mlflow(self):
        tracking_uri = os.getenv("MLFLOW_TRACKING_URI", "http://mlflow_server:5000")
        mlflow.set_tracking_uri(tracking_uri)
        mlflow.set_experiment("Fraud_Detection_Architecture")
        
        with mlflow.start_run():
            accuracy = self.train()
            mlflow.log_param("n_estimators", 100)
            mlflow.log_metric("accuracy", accuracy)
            mlflow.sklearn.log_model(self.model, "fraud_rf_model")
            print(f"[MLFLOW] Run enregistré avec succès. Accuracy: {accuracy}")

app = FastAPI(title="Pipeline Transformation & Modélisation")

@app.post("/run-pipeline")
def run_all():
    try:
        # 1. Transformation du fichier CSV partagé
        transformer = DataTransformer("/data/raw_data.csv", "/data/cleaned_data.csv")
        clean_path = transformer.run_pipeline()
        
        # 2. Modélisation et envoi vers MLflow
        trainer = ModelTrainer(clean_path)
        trainer.log_mlflow()
        
        return {"status": "success", "message": "Pipeline complet (Anonymisation + MLflow) exécuté avec succès."}
    except Exception as e:
        print("💥 CRASH DU PIPELINE (DÉTAIL PYTHON) :")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)