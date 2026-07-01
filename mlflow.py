import os
import pandas as pd
import psycopg2
from sqlalchemy import create_engine
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score
import mlflow
import mlflow.sklearn
from fastapi import FastAPI, HTTPException
import uvicorn

# =====================================================================
# CLASSE: Gestionnaire de Base de Données
# =====================================================================
class DatabaseManager:
    def __init__(self, host, port, database, user, password):
        self.host = host
        self.port = port
        self.database = database
        self.user = user
        self.password = password
        self.engine = None

    def connect(self):
        try:
            url = f"postgresql://{self.user}:{self.password}@{self.host}:{self.port}/{self.database}"
            self.engine = create_engine(url)
            print("[INFO] Connexion SQLAlchemy établie.")
        except Exception as e:
            print(f"[ERROR] Erreur connexion : {e}")
            raise

    def read_table(self, query):
        if self.engine is None: self.connect()
        return pd.read_sql(query, self.engine)

# =====================================================================
# CLASSE: Entraîneur de Modèle
# =====================================================================
class ModelTrainer:
    def __init__(self, dataframe, target="Is Fraud"):
        self.dataframe = dataframe
        self.target = target
        self.model = RandomForestClassifier(n_estimators=100, max_depth=10, random_state=42)

    def prepare_data(self):
        # Exclusion des colonnes non-numériques pour la modélisation
        X = self.dataframe.select_dtypes(include=['number']).drop(columns=[self.target], errors='ignore')
        y = self.dataframe[self.target]
        return train_test_split(X, y, test_size=0.2, random_state=42, stratify=y)

    def train(self):
        X_train, X_test, y_train, y_test = self.prepare_data()
        self.model.fit(X_train, y_train)
        preds = self.model.predict(X_test)
        return accuracy_score(y_test, preds)

    def log_mlflow(self):
        #  CORRECTION EXTRÊME : Passage par la passerelle de l'hôte physique (Zéro déconnexion)
        tracking_uri = os.getenv("MLFLOW_TRACKING_URI", "http://host.docker.internal:5000")
        mlflow.set_tracking_uri(tracking_uri)
        mlflow.set_experiment("Fraud_Detection_Architecture")

        with mlflow.start_run():
            acc = self.train()
            mlflow.log_param("n_estimators", self.model.n_estimators)
            mlflow.log_param("max_depth", self.model.max_depth)
            mlflow.log_metric("accuracy", acc)
            mlflow.sklearn.log_model(self.model, "fraud_rf_model")
            print(f"[SUCCESS] Modèle enregistré dans MLflow via Host Gateway. Accuracy: {acc}")

# =====================================================================
# CLASSE: Orchestrateur (Pipeline)
# =====================================================================
class Pipeline:
    def __init__(self):
        self.db = DatabaseManager(
            host=os.getenv("DB_HOST", "postgres_memoire"),
            port=5432,
            database="memoire",
            user="postgres",
            password="postgres"
        )

    def run(self):
        # OPTIMISATION TEMPORELLE : Ajout d'un LIMIT pour valider la mécanique Airflow instantanément
        # Tu retireras le "LIMIT 20000" uniquement pour les exécutions finales de ton mémoire !
        query = "SELECT * FROM public.bank_transactions LIMIT 20000;"
        df = self.db.read_table(query)
        
        trainer = ModelTrainer(df, target="Is Fraud")
        trainer.log_mlflow()

# =====================================================================
# SERVICE API (FastAPI)
# =====================================================================
app = FastAPI(title="ML Modeling Microservice")

@app.post("/run-pipeline")
def train_model():
    try:
        pipeline = Pipeline()
        pipeline.run()
        return {"status": "success", "message": "Entraînement et tracking MLflow terminés avec succès."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)