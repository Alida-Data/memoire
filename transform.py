import os
import hashlib
import pandas as pd
import numpy as np
import psycopg2
from sqlalchemy import create_engine
from sklearn.model_selection import train_test_split
from xgboost import XGBClassifier  
from sklearn.metrics import f1_score, accuracy_score, confusion_matrix, ConfusionMatrixDisplay, roc_curve, auc
import matplotlib.pyplot as plt
import mlflow  # Package officiel de tracking
import mlflow.xgboost  # Extension XGBoost officielle
from fastapi import FastAPI, HTTPException
import uvicorn
import traceback
from imblearn.combine import SMOTETomek  # Pour surmonter le déséquilibre extrême

# =====================================================================
# CLASSE: Nettoyage et Transformation (Anonymisation)
# =====================================================================
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
        
        #  SÉCURITÉ : Nettoyage des colonnes parasites contenant des dictionnaires (ex: erreurs JSON précédentes)
        for col in df.columns:
            if df[col].astype(str).str.contains('num_transactions').any():
                print(f"[WARNING] Colonne parasite supprimée du traitement : {col}")
                df = df.drop(columns=[col])

        if 'transaction_id' in df.columns:
            df = df.drop_duplicates(subset=['transaction_id'], keep='first')
        else:
            df = df.drop_duplicates()
            
        if 'is_fraud' in df.columns:
            df = df.dropna(subset=['is_fraud'])
            def convert_fraud_val(val):
                if pd.isnull(val): return None
                v_str = str(val).strip().lower()
                if v_str in ['yes', '1', '1.0', 'true']: return 1
                if v_str in ['no', '0', '0.0', 'false']: return 0
                return None
                
            df['is_fraud'] = df['is_fraud'].apply(convert_fraud_val)
            df = df.dropna(subset=['is_fraud'])
            if not df.empty:
                df['is_fraud'] = df['is_fraud'].astype(int)
                
        if 'card_number' in df.columns:
            df['card_number'] = df['card_number'].apply(self._anonymize_card)
            
        return df

    def run_pipeline(self) -> str:
        if not os.path.exists(self.raw_path):
            print(f"[WARNING] Fichier brut {self.raw_path} non trouvé. Étape ignorée.")
            return None
        if os.path.exists(self.cleaned_path):
            os.remove(self.cleaned_path)
            
        is_first_chunk = True
        for chunk in pd.read_csv(self.raw_path, chunksize=self.chunk_size):
            cleaned_chunk = self.clean_chunk(chunk)
            if not cleaned_chunk.empty:
                cleaned_chunk.to_csv(self.cleaned_path, mode='a', index=False, header=is_first_chunk)
                is_first_chunk = False
        return self.cleaned_path

# =====================================================================
# CLASSE: Gestionnaire de Base de Données (PostgreSQL)
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
            print(f"[ERROR] Erreur connexion PostgreSQL : {e}")
            raise

    def read_table(self, query):
        if self.engine is None: self.connect()
        return pd.read_sql(query, self.engine)

# =====================================================================
# CLASSE: Entraîneur de Modèle (XGBoost + SMOTE-Tomek + MLflow)
# =====================================================================
class ModelTrainer:
    def __init__(self, dataframe, target="is_fraud"):
        self.dataframe = dataframe
        self.target = target
        
        #  CONFIGURATION DES HYPERPARAMÈTRES AVANCÉS POUR LE 95%+
        self.params = {
            "n_estimators": 800,           # Augmenté pour capturer les interactions complexes
            "max_depth": 7,                # Légèrement augmenté pour l'espace des variables comportementales
            "learning_rate": 0.05,         # Plus faible pour une convergence robuste et sans surapprentissage
            "subsample": 0.8,              # Prévient l'overfitting sur les transactions légitimes répétitives
            "colsample_bytree": 0.8,       # Force chaque arbre à regarder un sous-ensemble de variables
            "eval_metric": "aucpr",        # CRUCIAL : Optimise la Précision et le Rappel (PR-AUC) au lieu de l'accuracy pure
            "random_state": 42
        }
        self.model = XGBClassifier(**self.params)

    def prepare_data(self):
        X = self.dataframe.select_dtypes(include=['number']).drop(columns=[self.target], errors='ignore')
        y = self.dataframe[self.target].astype(int)
        return train_test_split(X, y, test_size=0.2, random_state=42, stratify=y)

    def log_mlflow(self):
        tracking_uri = os.getenv("MLFLOW_TRACKING_URI", "http://mlflow_server:5000")
        mlflow.set_tracking_uri(tracking_uri)
        mlflow.set_experiment("Detection_Fraude_Financial")

        X_train, X_test, y_train, y_test = self.prepare_data()

        #  APPLICATION DE SMOTE-TOMEK : Nettoie les frontières de classes et crée des fraudes synthétiques
        print("[INFO] Application de SMOTE-Tomek sur le dataset d'entraînement...")
        smt = SMOTETomek(random_state=42)
        X_train_res, y_train_res = smt.fit_resample(X_train, y_train)

        with mlflow.start_run(run_name="Entrainement_XGBoost_Haute_Precision"):
            mlflow.log_params(self.params)
            
            # Entraînement sur les données rééquilibrées
            self.model.fit(
                X_train_res, y_train_res,
                eval_set=[(X_test, y_test)],
                verbose=False
            )
            
            y_pred = self.model.predict(X_test)
            y_pred_proba = self.model.predict_proba(X_test)[:, 1]
            
            # Évaluation basée sur les métriques réelles requises
            f1 = f1_score(y_test, y_pred, average='binary') # Changé en binary pour refléter la classe positive (Fraude)
            accuracy = accuracy_score(y_test, y_pred)
            
            mlflow.log_metric("f1_score", f1)
            mlflow.log_metric("accuracy", accuracy)
            mlflow.set_tag("Statut", "Pipeline_Production_Valide")
            
            try:
                # 1. Matrice de Confusion
                plt.figure(figsize=(6, 6))
                cm = confusion_matrix(y_test, y_pred)
                disp = ConfusionMatrixDisplay(confusion_matrix=cm, display_labels=['Normal', 'Fraude'])
                disp.plot(cmap='Blues', values_format='d')
                plt.title("Matrice de Confusion Optimisée")
                plt.savefig("confusion_matrix.png", bbox_inches='tight')
                mlflow.log_artifact("confusion_matrix.png")
                plt.close()

                # 2. Courbe ROC
                plt.figure(figsize=(6, 6))
                fpr, tpr, _ = roc_curve(y_test, y_pred_proba)
                roc_auc = auc(fpr, tpr)
                plt.plot(fpr, tpr, color='darkorange', lw=2, label=f'ROC curve (AUC = {roc_auc:.2f})')
                plt.plot([0, 1], [0, 1], color='navy', lw=2, linestyle='--')
                plt.xlabel('Taux de Faux Positifs')
                plt.ylabel('Taux de Vrais Positifs')
                plt.title("Courbe ROC - Version Haute Précision")
                plt.legend(loc="lower right")
                plt.savefig("roc_curve.png", bbox_inches='tight')
                mlflow.log_artifact("roc_curve.png")
                plt.close()
                print("[INFO] Graphiques sauvegardés et transmis comme Artifacts à MLflow.")
            except Exception as graph_err:
                print(f"[WARNING] Erreur lors de la génération des graphiques : {graph_err}")

            # Enregistrement officiel et versioning automatique du modèle
            mlflow.xgboost.log_model(
                xgb_model=self.model, 
                artifact_path="model_fraude",
                registered_model_name="XGBoost_Fraude_Model"
            )
            print(f"[SUCCESS] Modèle XGBoost poussé sur MLflow. Nouveau F1-Score: {f1:.4f}")

# =====================================================================
# SERVICE API (FastAPI) - Routes Découplées pour Airflow
# =====================================================================
app = FastAPI(title="ML Modeling Microservice")

@app.post("/transform-only")
@app.post("/transform")  
def transform_only():
    """Étape 2 du pipeline : Nettoyage et anonymisation du CSV brut"""
    try:
        print("[INFO] Début du nettoyage et de l'anonymisation du CSV...")
        transformer = DataTransformer("/data/raw_data.csv", "/data/cleaned_data.csv")
        transformer.run_pipeline()
        return {"status": "success", "message": "Données nettoyées et anonymisées dans /data/cleaned_data.csv."}
    except Exception as e:
        print("CRASH DURANT LA TRANSFORMATION :")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Erreur Transformation: {str(e)}")

@app.post("/train-only")
def train_only():
    """Étape 4 du pipeline : Lecture de PostgreSQL et entraînement XGBoost + MLflow"""
    try:
        db = DatabaseManager(
            host=os.getenv("DB_HOST", "postgres_memoire"),
            port=5432,
            database="memoire",
            user="postgres",
            password="postgres"
        )
        
        # 1. Requête SQL avec guillemets doubles pour PostgreSQL
        # 1. Extraction globale sécurisée pour contourner le typage strict de PostgreSQL
        query = """
            SELECT * FROM public.bank_transactions_cleaned 
            LIMIT 150000;
        """
        print("[INFO] Lecture globale des données chargées dans PostgreSQL...")
        df_raw = db.read_table(query)
        
        # 2. Nettoyage immédiat de la casse et des guillemets dans Pandas
        df_raw.columns = df_raw.columns.str.replace('"', '').str.strip().str.lower()
        
        # 3. Sélection stricte des features requises dans Pandas
        features_list = ['amount', 'high_risk_merchant', 'transaction_hour', 'weekend_transaction', 'velocity_last_hour', 'is_fraud']
        
        # On ne garde que les colonnes qui existent réellement après normalisation
        df = df_raw[[col for col in features_list if col in df_raw.columns]].copy()
        print(f"[INFO] Colonnes récupérées avec succès : {list(df.columns)}")
        
        # 4. Gestion stricte des types numériques
        for col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
        
        # 5. Lancement du rééchantillonnage et de l'entraînement MLOps
        trainer = ModelTrainer(df, target="is_fraud")
        trainer.log_mlflow()
        
        return {"status": "success", "message": "Modèle XGBoost entraîné avec succès depuis PostgreSQL et enregistré sur MLflow."}
    except Exception as e:
        print(" CRASH DURANT L'ENTRAÎNEMENT MLOPS :")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Erreur Entraînement: {str(e)}")
    

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)