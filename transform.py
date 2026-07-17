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

# Désactiver l'interface graphique de Matplotlib pour éviter les bugs de mémoire dans Docker
import matplotlib
matplotlib.use('Agg')

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

    def load_csv_chunks(self, csv_path: str, table_name: str, chunk_size: int = 100000):
        """Vide la table cible et injecte un fichier CSV par blocs (chunks) pour optimiser la mémoire RAM."""
        if self.engine is None: 
            self.connect()

        print(f"[INFO] Nettoyage (TRUNCATE) de la table public.{table_name}...")
        with self.engine.begin() as conn:
            conn.execute(f"TRUNCATE TABLE public.{table_name} RESTART IDENTITY CASCADE;")

        print(f"[INFO] Début de l'injection de {csv_path} dans la table public.{table_name}...")
        for i, chunk in enumerate(pd.read_csv(csv_path, chunksize=chunk_size)):
            # Nettoyage uniforme des noms de colonnes
            chunk.columns = chunk.columns.str.strip().str.lower().str.replace('"', '')
            
            # Injection par blocs
            chunk.to_sql(table_name, self.engine, if_exists='append', index=False)
            print(f"[INFO] Bloc {i + 1} inséré avec succès ({len(chunk)} lignes).")


# =====================================================================
# CLASSE: Entraîneur de Modèle (XGBoost + SMOTE-Tomek + MLflow)
# =====================================================================
class ModelTrainer:
    def __init__(self, dataframe, target="is_fraud"):
        self.dataframe = dataframe
        self.target = target
        
        # CONFIGURATION DES HYPERPARAMÈTRES OPTIMISÉS
        self.params = {
            "n_estimators": 800,           
            "max_depth": 7,                
            "learning_rate": 0.03,         # Baissé à 0.03 pour affiner la convergence avec SMOTE
            "subsample": 0.8,              
            "colsample_bytree": 0.8,       
            "eval_metric": "aucpr",        # Focus sur la courbe Précision-Rappel
            "random_state": 42
        }
        self.model = XGBClassifier(**self.params, early_stopping_rounds=50)

    def prepare_data(self):
        X = self.dataframe.select_dtypes(include=['number']).drop(columns=[self.target], errors='ignore')
        y = self.dataframe[self.target].astype(int)
        return train_test_split(X, y, test_size=0.2, random_state=42, stratify=y)

    def log_mlflow(self):
        tracking_uri = os.getenv("MLFLOW_TRACKING_URI", "http://mlflow_server:5000")
        mlflow.set_tracking_uri(tracking_uri)
        mlflow.set_experiment("Detection_Fraude_Financial")

        X_train, X_test, y_train, y_test = self.prepare_data()

        # APPLICATION DE SMOTE-TOMEK
        print("[INFO] Application de SMOTE-Tomek sur le dataset d'entraînement...")
        smt = SMOTETomek(random_state=42)
        X_train_res, y_train_res = smt.fit_resample(X_train, y_train)

        with mlflow.start_run(run_name="Entrainement_XGBoost_Haute_Precision"):
            mlflow.log_params(self.params)
            
            self.model.fit(
                X_train_res, y_train_res,
                eval_set=[(X_test, y_test)],
                verbose=False
            )
            
            y_pred = self.model.predict(X_test)
            y_pred_proba = self.model.predict_proba(X_test)[:, 1]
            
            f1 = f1_score(y_test, y_pred, average='binary')
            accuracy = accuracy_score(y_test, y_pred)
            
            mlflow.log_metric("f1_score", f1)
            mlflow.log_metric("accuracy", accuracy)
            mlflow.set_tag("Statut", "Pipeline_Production_Valide")
            
            # --- GÉNÉRATION ET ENVOI DES GRAPHES VERS ARTIFACTS ---
            try:
                cm_path = "/tmp/confusion_matrix.png"
                roc_path = "/tmp/roc_curve.png"

                # 1. Matrice de Confusion
                plt.figure(figsize=(6, 6))
                cm = confusion_matrix(y_test, y_pred)
                disp = ConfusionMatrixDisplay(confusion_matrix=cm, display_labels=['Normal', 'Fraude'])
                disp.plot(cmap='Blues', values_format='d')
                plt.title("Matrice de Confusion Optimisée")
                plt.savefig(cm_path, bbox_inches='tight')
                mlflow.log_artifact(cm_path)
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
                plt.savefig(roc_path, bbox_inches='tight')
                mlflow.log_artifact(roc_path)
                plt.close()
                print("[INFO] Graphiques sauvegardés dans /tmp/ et transmis à MLflow.")
            except Exception as graph_err:
                print(f"[CRITICAL ERROR GRAPHES] Erreur : {graph_err}")
                traceback.print_exc()

# =====================================================================
# SERVICE API (FastAPI)
# =====================================================================
app = FastAPI(title="ML Modeling Microservice")

@app.post("/load-raw")
def load_raw():
    """Déclenche l'import direct du CSV brut dans la table public.bank_transactions."""
    try:
        raw_path = "/data/raw_data.csv"
        table_name = "bank_transactions"
        
        if not os.path.exists(raw_path):
            raise HTTPException(status_code=404, detail=f"Fichier brut {raw_path} non trouvé dans le volume.")
            
        db = DatabaseManager(
            host=os.getenv("DB_HOST", "postgres_memoire"),
            port=5432,
            database="memoire",
            user="postgres",
            password="postgres"
        )
        
        db.load_csv_chunks(csv_path=raw_path, table_name=table_name, chunk_size=100000)
        return {"status": "success", "message": f"Données brutes chargées avec succès dans public.{table_name}."}
    except Exception as e:
        print("CRASH DURANT LE CHARGEMENT DE LA TABLE BRUTE :")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Erreur d'importation : {str(e)}")


@app.post("/transform-only")
@app.post("/transform")  
def transform_only():
    """Effectue l'anonymisation et le nettoyage locaux, produit cleaned_data.csv."""
    try:
        print("[INFO] Début du nettoyage et de l'anonymisation du CSV...")
        transformer = DataTransformer("/data/raw_data.csv", "/data/cleaned_data.csv")
        transformer.run_pipeline()
        return {"status": "success", "message": "Données nettoyées et anonymisées dans /data/cleaned_data.csv."}
    except Exception as e:
        print("CRASH DURANT LA TRANSFORMATION :")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Erreur Transformation: {str(e)}")


@app.post("/load-cleaned")
def load_cleaned():
    """Déclenche l'import du CSV nettoyé et anonymisé dans la table public.bank_transactions_cleaned."""
    try:
        cleaned_path = "/data/cleaned_data.csv"
        table_name = "bank_transactions_cleaned"
        
        if not os.path.exists(cleaned_path):
            raise HTTPException(status_code=404, detail=f"Fichier nettoyé {cleaned_path} non trouvé. Exécutez d'abord /transform.")
            
        db = DatabaseManager(
            host=os.getenv("DB_HOST", "postgres_memoire"),
            port=5432,
            database="memoire",
            user="postgres",
            password="postgres"
        )
        
        db.load_csv_chunks(csv_path=cleaned_path, table_name=table_name, chunk_size=100000)
        return {"status": "success", "message": f"Données nettoyées chargées avec succès dans public.{table_name}."}
    except Exception as e:
        print("CRASH DURANT LE CHARGEMENT DE LA TABLE NETTOYÉE :")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Erreur d'importation : {str(e)}")


@app.post("/train-only")
def train_only():
    """Entraîne le modèle en se basant sur la table propre de Postgres."""
    try:
        db = DatabaseManager(
            host=os.getenv("DB_HOST", "postgres_memoire"),
            port=5432,
            database="memoire",
            user="postgres",
            password="postgres"
        )
        
        # Lecture depuis la table nettoyée
        query = """
            SELECT * FROM public.bank_transactions_cleaned 
            LIMIT 150000;
        """
        print("[INFO] Lecture globale des données propres chargées dans PostgreSQL...")
        df_raw = db.read_table(query)
        
        df_raw.columns = df_raw.columns.str.replace('"', '').str.strip().str.lower()
        
        features_list = ['amount', 'high_risk_merchant', 'transaction_hour', 'weekend_transaction', 'velocity_last_hour', 'is_fraud']
        
        df = df_raw[[col for col in features_list if col in df_raw.columns]].copy()
        print(f"[INFO] Colonnes récupérées avec succès : {list(df.columns)}")
        
        for col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
        
        trainer = ModelTrainer(df, target="is_fraud")
        trainer.log_mlflow()
        
        return {"status": "success", "message": "Modèle XGBoost entraîné avec succès depuis PostgreSQL et enregistré sur MLflow."}
    except Exception as e:
        print(" CRASH DURANT L'ENTRAÎNEMENT MLOPS :")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Erreur Entraînement: {str(e)}")

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)