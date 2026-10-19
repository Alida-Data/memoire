import os
import hashlib
import pandas as pd
import numpy as np
import psycopg2
from sqlalchemy import create_engine
from sklearn.model_selection import train_test_split, RandomizedSearchCV, StratifiedKFold
from xgboost import XGBClassifier  
from sklearn.metrics import f1_score, accuracy_score, precision_score, recall_score, confusion_matrix, ConfusionMatrixDisplay, roc_curve, auc
import matplotlib.pyplot as plt
import mlflow  # Package officiel de tracking
import mlflow.xgboost  # Extension XGBoost officielle
from fastapi import FastAPI, HTTPException
import uvicorn
import json
import traceback
from imblearn.over_sampling import SMOTE  # Plus rapide que SMOTETomek sur gros volumes
from imblearn.pipeline import Pipeline as ImbPipeline
from prometheus_fastapi_instrumentator import Instrumentator

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
            # Utilisation directe de os.environ pour lever une KeyError si HASH_SALT est manquant
            salt = os.environ["HASH_SALT"].encode('utf-8')
            return hashlib.sha256(str(card_number).encode('utf-8') + salt).hexdigest()
        return None

    def clean_chunk(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        
        # 1. Suppression des colonnes parasites
        for col in df.columns:
            if df[col].astype(str).str.contains('num_transactions').any():
                print(f"[WARNING] Colonne parasite supprimée du traitement : {col}")
                df = df.drop(columns=[col])

        # 2. Déduplication
        if 'transaction_id' in df.columns:
            df = df.drop_duplicates(subset=['transaction_id'], keep='first')
        else:
            df = df.drop_duplicates()
            
        # 3. Nettoyage de la cible is_fraud
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
                
        # 4. PPDA : Hachage salé des cartes bancaires (supporte 'card_number' et 'cc_num')
        if 'card_number' in df.columns:
            df['card_number'] = df['card_number'].apply(self._anonymize_card)
        elif 'cc_num' in df.columns:
            df['cc_num'] = df['cc_num'].apply(self._anonymize_card)

        # 5. PPDA : Floutage GPS / K-Anonymat (Arrondi à 1 décimale ~11km)
        if 'lat' in df.columns and 'long' in df.columns:
            df['lat'] = df['lat'].round(1)
            df['long'] = df['long'].round(1)
            
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
        if self.engine is None: 
            self.connect()
        conn = self.engine.raw_connection()
        try:
            return pd.read_sql(str(query), con=conn)
        finally:
            conn.close()

    def load_csv_chunks(self, csv_path: str, table_name: str, chunk_size: int = 100000):
        if self.engine is None: 
            self.connect()
        print(f"[INFO] Nettoyage (TRUNCATE) de la table public.{table_name}...")
        with self.engine.begin() as conn:
            conn.exec_driver_sql(f"TRUNCATE TABLE public.{table_name} RESTART IDENTITY CASCADE;")

        print(f"[INFO] Début de l injection de {csv_path} dans la table public.{table_name}...")
        with self.engine.begin() as conn:
            for i, chunk in enumerate(pd.read_csv(csv_path, chunksize=chunk_size)):
                chunk.columns = chunk.columns.str.strip().str.lower().str.replace('"', '')
                chunk.to_sql(table_name, con=conn, if_exists='append', index=False)
                print(f"[INFO] Bloc {i + 1} inséré avec succès ({len(chunk)} lignes).")
class ModelTrainer:
    def __init__(self, dataframe, target="is_fraud"):
        self.dataframe = dataframe
        self.target = target
        self.model = None

    def prepare_data(self):
        X = self.dataframe.drop(columns=[self.target], errors='ignore')
        X = pd.get_dummies(X, drop_first=True)
        X = X.astype(np.float32)
        y = self.dataframe[self.target].astype(int)
        return train_test_split(X, y, test_size=0.2, random_state=42, stratify=y)

    def log_mlflow(self):
        tracking_uri = os.getenv("MLFLOW_TRACKING_URI", "http://mlflow_proxy:5000")
        mlflow.set_tracking_uri(tracking_uri)
        mlflow.set_experiment("Fraud_Detection_Pipeline")

        X_train, X_test, y_train, y_test = self.prepare_data()
        model_columns = X_train.columns.tolist()

        pipeline = ImbPipeline([
            ('resample', SMOTE(random_state=42)),
            ('clf', XGBClassifier(eval_metric='aucpr', random_state=42, n_jobs=1)),
        ])

        param_distributions = {
            'resample__sampling_strategy': [0.3, 0.5, 0.7, 1.0],
            'clf__n_estimators': [300, 500, 800],
            'clf__max_depth': [6, 8, 10],
            'clf__learning_rate': [0.01, 0.03, 0.05, 0.1],
            'clf__subsample': [0.7, 0.8, 0.9],
            'clf__colsample_bytree': [0.6, 0.7, 0.8],
            'clf__min_child_weight': [1, 2, 3],
            'clf__gamma': [0, 0.1, 0.2],
            'clf__scale_pos_weight': [1, 3, 5]
        }

        cv = StratifiedKFold(n_splits=3, shuffle=True, random_state=42)

        print("[INFO] Recherche d'hyperparamètres en cours...")
        search = RandomizedSearchCV(
            pipeline,
            param_distributions=param_distributions,
            n_iter=12,
            scoring='f1',
            cv=cv,
            n_jobs=-1,
            random_state=42,
            verbose=1,
            refit=True,
        )
        search.fit(X_train, y_train)

        self.model = search.best_estimator_.named_steps['clf']

        with mlflow.start_run(run_name="Entrainement_XGBoost_Haute_Precision"):
            mlflow.log_params({f"best_{k}": v for k, v in search.best_params_.items()})
            mlflow.log_metric("cv_best_f1", search.best_score_)

            y_pred_proba = self.model.predict_proba(X_test)[:, 1]

            meilleur_seuil = 0.5
            meilleur_f1 = 0.0
            for threshold in np.arange(0.1, 0.9, 0.02):
                y_pred_temp = (y_pred_proba >= threshold).astype(int)
                score = f1_score(y_test, y_pred_temp, pos_label=1)
                if score > meilleur_f1:
                    meilleur_f1 = score
                    meilleur_seuil = threshold

            y_pred = (y_pred_proba >= meilleur_seuil).astype(int)

            mlflow.log_param("best_threshold", round(meilleur_seuil, 2))
            mlflow.log_metric("f1_score", meilleur_f1)
            mlflow.log_metric("accuracy", accuracy_score(y_test, y_pred))
            mlflow.log_metric("precision", precision_score(y_test, y_pred, pos_label=1, zero_division=0))
            mlflow.log_metric("recall", recall_score(y_test, y_pred, pos_label=1, zero_division=0))
            mlflow.set_tag("Statut", "Pipeline_Production_Valide")

            # 1. Sauvegarde locale dans shared_data pour FastAPI / Inférence
            os.makedirs("/data", exist_ok=True)
            self.model.save_model("/data/fraud_model.json")
            with open("/data/model_columns.json", "w") as f:
                json.dump(model_columns, f)
            with open("/data/threshold.json", "w") as f:
                json.dump({"threshold": round(float(meilleur_seuil), 4)}, f)

            # 2. Enregistrement direct dans MLflow via l'API native (mémoire/HTTP)
            mlflow.log_dict({"threshold": round(float(meilleur_seuil), 4)}, "threshold.json")
            mlflow.log_dict(model_columns, "model_columns.json")
            mlflow.xgboost.log_model(self.model, artifact_path="model")

            # 3. Génération et enregistrement des graphiques
            try:
                plt.figure(figsize=(6, 6))
                cm = confusion_matrix(y_test, y_pred)
                disp = ConfusionMatrixDisplay(confusion_matrix=cm, display_labels=['Normal', 'Fraude'])
                disp.plot(cmap='Blues', values_format='d')
                plt.title("Matrice de Confusion Optimisée")
                cm_path = "/tmp/confusion_matrix.png"
                plt.savefig(cm_path, bbox_inches='tight')
                plt.close()
                mlflow.log_artifact(cm_path)

                plt.figure(figsize=(6, 5), dpi=300)
                fpr, tpr, _ = roc_curve(y_test, y_pred_proba)
                plt.plot(fpr, tpr, color="#ff8c00", lw=2.5) 
                plt.plot([0, 1], [0, 1], color="#000080", lw=2, linestyle="--")
                plt.xlim([0.0, 1.0])
                plt.ylim([0.0, 1.05])
                plt.title("Courbe ROC - Version Haute Précision", fontsize=12, pad=10)
                plt.xlabel("Taux de Faux Positifs", fontsize=11)
                plt.ylabel("Taux de Vrais Positifs", fontsize=11)
                roc_path = "/tmp/roc_curve.png"
                plt.savefig(roc_path, bbox_inches='tight')
                plt.close()
                mlflow.log_artifact(roc_path)
            except Exception as graph_err:
                print(f"[CRITICAL ERROR GRAPHES] Erreur : {graph_err}")
# =====================================================================
# SERVICE API (FastAPI)
# =====================================================================
app = FastAPI(title="ML Modeling Microservice")
Instrumentator().instrument(app).expose(app)

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
        
        query = """
            SELECT * FROM public.bank_transactions_cleaned 
            ORDER BY transaction_id
            LIMIT 150000;
        """
        print("[INFO] Lecture globale des données propres chargées dans PostgreSQL...")
        df_raw = db.read_table(query)
        
        df_raw.columns = df_raw.columns.str.replace('"', '').str.strip().str.lower()

        if 'customer_id' in df_raw.columns and 'timestamp' in df_raw.columns:
            print("[INFO] Calcul réel de velocity_last_hour (fenêtre glissante de 1h par client)...")
            df_raw['timestamp'] = pd.to_datetime(df_raw['timestamp'])
            df_raw = df_raw.sort_values(['customer_id', 'timestamp'])
            df_raw = df_raw.set_index('timestamp')
            df_raw['velocity_last_hour'] = (
                df_raw.groupby('customer_id')['amount']
                .rolling('1h', closed='left')
                .count()
                .reset_index(level=0, drop=True)
            )
            df_raw = df_raw.reset_index()
            print(f"[INFO] velocity_last_hour calculée — exemple de distribution : {df_raw['velocity_last_hour'].describe().to_dict()}")
        else:
            print("[WARNING] customer_id ou timestamp absent : velocity_last_hour restera à 0.")

        numeric_features = ['amount', 'high_risk_merchant', 'transaction_hour', 'weekend_transaction', 'velocity_last_hour', 'card_present']
        categorical_features = ['merchant_type', 'card_type', 'device', 'channel', 'country', 'city_size', 'currency']
        features_list = numeric_features + categorical_features + ['is_fraud']

        df = df_raw[[col for col in features_list if col in df_raw.columns]].copy()
        print(f"[INFO] Colonnes récupérées avec succès : {list(df.columns)}")

        for col in numeric_features:
            if col in df.columns:
                if col == 'card_present':
                    df[col] = df[col].astype(bool).astype(int)
                else:
                    df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
        for col in categorical_features:
            if col in df.columns:
                df[col] = df[col].fillna('unknown').astype(str)
        
        trainer = ModelTrainer(df, target="is_fraud")
        trainer.log_mlflow()
        
        return {"status": "success", "message": "Modèle XGBoost entraîné avec succès depuis PostgreSQL et enregistré sur MLflow."}
    except Exception as e:
        print(" CRASH DURANT L'ENTRAÎNEMENT MLOPS :")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Erreur Entraînement: {str(e)}")

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)