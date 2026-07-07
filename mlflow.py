import os
import pandas as pd
import psycopg2
from sqlalchemy import create_engine
from sklearn.model_selection import train_test_split
from xgboost import XGBClassifier  
from sklearn.metrics import f1_score, accuracy_score, confusion_matrix, ConfusionMatrixDisplay, roc_curve, auc
import matplotlib.pyplot as plt
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
            print("[INFO] Connexion SQLAlchemy établie avec PostgreSQL.")
        except Exception as e:
            print(f"[ERROR] Erreur connexion : {e}")
            raise

    def read_table(self, query):
        if self.engine is None: self.connect()
        return pd.read_sql(query, self.engine)

# =====================================================================
# CLASSE: Entraîneur de Modèle (Optimisé avec scale_pos_weight & features réelles)
# =====================================================================
class ModelTrainer:
    def __init__(self, dataframe, target="is_fraud"):
        self.dataframe = dataframe
        self.target = target
        
        # Calcul du ratio exact pour scale_pos_weight (Gestion du déséquilibre ~80/20)
        nb_neg = (self.dataframe[self.target] == 0).sum()
        nb_pos = (self.dataframe[self.target] == 1).sum()
        ratio = (nb_neg / nb_pos) if nb_pos > 0 else 1.0

        # Configuration des hyperparamètres XGBoost pour maximiser le F1-Score
        self.params = {
            "n_estimators": 150,
            "max_depth": 6,
            "learning_rate": 0.1,
            "scale_pos_weight": ratio,     # Équilibrage natif des classes
            "random_state": 42
        }
        self.model = XGBClassifier(**self.params)

    def prepare_data(self):
        # Conversion explicite en types numériques si nécessaire et exclusion de la cible
        X = self.dataframe.select_dtypes(include=['number']).drop(columns=[self.target], errors='ignore')
        y = self.dataframe[self.target].astype(int)
        return train_test_split(X, y, test_size=0.2, random_state=42, stratify=y)

    def log_mlflow(self):
        tracking_uri = os.getenv("MLFLOW_TRACKING_URI", "http://host.docker.internal:5000")
        mlflow.set_tracking_uri(tracking_uri)
        mlflow.set_experiment("Detection_Fraude_Financial")

        X_train, X_test, y_train, y_test = self.prepare_data()

        with mlflow.start_run(run_name="Entrainement_XGBoost_Final_Cleaned"):
            # Logging des hyperparamètres
            mlflow.log_params(self.params)
            
            # Entraînement de l'algorithme
            self.model.fit(X_train, y_train)
            
            # Calcul des prédictions et des probabilités
            y_pred = self.model.predict(X_test)
            y_pred_proba = self.model.predict_proba(X_test)[:, 1]
            
            # Évaluation des KPI requis pour le mémoire
            f1 = f1_score(y_test, y_pred, average='macro')
            accuracy = accuracy_score(y_test, y_pred)
            
            mlflow.log_metric("f1_score", f1)
            mlflow.log_metric("accuracy", accuracy)
            mlflow.set_tag("Statut", "Pipeline_Production_Valide")
            
            # --- GÉNÉRATION ET LOG DES VISUELS DE HAUTE QUALITÉ ---
            try:
                # 1. Matrice de Confusion
                plt.figure(figsize=(6, 6))
                cm = confusion_matrix(y_test, y_pred)
                disp = ConfusionMatrixDisplay(confusion_matrix=cm, display_labels=['Normal', 'Fraude'])
                disp.plot(cmap='Blues')
                plt.title("Matrice de Confusion - Pipeline Nettoyé")
                plt.savefig("confusion_matrix.png", bbox_inches='tight')
                mlflow.log_artifact("confusion_matrix.png")
                plt.close()

                # 2. Courbe ROC
                plt.figure(figsize=(6, 6))
                fpr, tpr, _ = roc_curve(y_test, y_pred_proba)
                roc_auc = auc(fpr, tpr)
                plt.plot(fpr, tpr, color='darkorange', lw=2, label=f'ROC curve (AUC = {roc_auc:.2f})')
                plt.plot([0, 1], [0, 1], color='navy', lw=2, linestyle='--')
                plt.xlabel("Taux de Faux Positifs (FPR)")
                plt.ylabel("Taux de Vrais Positifs (TPR)")
                plt.title("Courbe ROC - Modèle XGBoost")
                plt.legend(loc="lower right")
                plt.savefig("roc_curve.png", bbox_inches='tight')
                mlflow.log_artifact("roc_curve.png")
                plt.close()
                print("[INFO] Graphiques analytiques stockés avec succès dans MLflow.")
            except Exception as graph_err:
                print(f"[WARNING] Erreur génération des artefacts : {graph_err}")

            # Enregistrement du modèle dans le registre MLOps
            mlflow.sklearn.log_model(
                sk_model=self.model, 
                artifact_path="model_fraude",
                registered_model_name="XGBoost_Fraude_Model"
            )

            print(f"[SUCCESS] Modèle entraîné. F1-Score: {f1:.4f} | Accuracy: {accuracy:.4f}")

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
        # Requête SQL utilisant le schéma d'ingestion réel extrait de DBeaver
        # Extraction de variables à fort pouvoir discriminant
        query = """
            SELECT 
                amount, 
                high_risk_merchant, 
                transaction_hour, 
                weekend_transaction, 
                velocity_last_hour, 
                is_fraud 
            FROM public.bank_transactions_cleaned 
            LIMIT 150000;
        """
        df = self.db.read_table(query)
        
        # Nettoyage à la volée des types natifs si PostgreSQL renvoie du texte
        for col in ['high_risk_merchant', 'transaction_hour', 'weekend_transaction', 'velocity_last_hour']:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
                
        trainer = ModelTrainer(df, target="is_fraud")
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
        return {"status": "success", "message": "Entraînement exécuté avec succès sur les colonnes réelles de bank_transactions_cleaned."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)