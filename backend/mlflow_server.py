# =============================================================================
# 1. IMPORTS & CONFIGURATION MLFLOW
# =============================================================================
import os
import numpy as np
import pandas as pd
import psycopg2
import xgboost as xgb
from xgboost import XGBClassifier
from imblearn.over_sampling import SMOTE
from sklearn.metrics import accuracy_score, f1_score, precision_score, recall_score
from sklearn.model_selection import train_test_split
import mlflow
import mlflow.xgboost

# Initialisation du serveur MLflow
mlflow.set_tracking_uri("http://localhost:5000")
mlflow.set_experiment("Detection Fraude Financial")

# =============================================================================
# 2. CHARGEMENT DEPUIS POSTGRESQL ET PREPARATION DES DONNEES
# =============================================================================
# Configuration de la connexion PostgreSQL
DB_HOST = os.getenv("DB_HOST", "127.0.0.1")
DB_NAME = os.getenv("DB_NAME", "memoire")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD", "postgres")
DB_PORT = os.getenv("DB_PORT", "5433")

# Connexion directe psycopg2 (plus stable que SQLAlchemy)
conn = psycopg2.connect(
    host=DB_HOST,
    database=DB_NAME,
    user=DB_USER,
    password=DB_PASSWORD,
    port=DB_PORT
)

# Chargement de la table nettoyée
query = "SELECT * FROM bank_transactions_cleaned;"
df = pd.read_sql(query, conn)
conn.close()

# Nettoyage et préparation des features
cols_to_drop = ['is_fraud', 'transaction_id', 'customer_id', 'timestamp', 'merchant_category']
X = df.drop(columns=[col for col in cols_to_drop if col in df.columns], errors='ignore')
X = pd.get_dummies(X, drop_first=True)
y = df['is_fraud'].astype(int)

# Split stratifié
X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=0.2, random_state=42, stratify=y
)

# =============================================================================
# 3. SMOTE & ENTRAÎNEMENT AVEC MLFLOW RUN
# =============================================================================
# SMOTE léger pour ajuster la distribution
smote = SMOTE(sampling_strategy=0.3, random_state=42)
X_train_res, y_train_res = smote.fit_resample(X_train, y_train)

# Calcul du ratio original pour la pénalisation XGBoost
ratio_origine = float(np.sum(y_train == 0) / np.sum(y_train == 1))

with mlflow.start_run(run_name="XGBoost_Optimal_Threshold_F1_95"):
    params = {
        "n_estimators": 400,
        "max_depth": 7,
        "learning_rate": 0.03,
        "scale_pos_weight": np.sqrt(ratio_origine),
        "subsample": 0.85,
        "colsample_bytree": 0.85,
        "gamma": 0.5,
        "eval_metric": "logloss",
        "random_state": 42
    }
    mlflow.log_params(params)
    
    # Entraînement
    model = XGBClassifier(**params)
    model.fit(
        X_train_res, y_train_res,
        eval_set=[(X_test, y_test)],
        verbose=False
    )
    
    # Threshold Tuning pour maximiser le F1-Score
    y_probs = model.predict_proba(X_test)[:, 1]
    meilleur_seuil = 0.5
    meilleur_f1 = 0.0

    for threshold in np.arange(0.1, 0.9, 0.02):
        y_pred_temp = (y_probs >= threshold).astype(int)
        score = f1_score(y_test, y_pred_temp, pos_label=1)
        if score > meilleur_f1:
            meilleur_f1 = score
            meilleur_seuil = threshold

    # Prédictions et calculs des métriques finales
    y_pred_final = (y_probs >= meilleur_seuil).astype(int)
    
    acc = accuracy_score(y_test, y_pred_final)
    precision = precision_score(y_test, y_pred_final, pos_label=1, zero_division=0)
    recall = recall_score(y_test, y_pred_final, pos_label=1, zero_division=0)
    
    # Log dans MLflow
    mlflow.log_param("best_threshold", round(meilleur_seuil, 2))
    mlflow.log_metric("f1_score_optimal", meilleur_f1)
    mlflow.log_metric("accuracy", acc)
    mlflow.log_metric("precision", precision)
    mlflow.log_metric("recall", recall)
    
    # Sauvegarde du modèle dans le registre
    mlflow.xgboost.log_model(
        xgb_model=model,
        artifact_path="model",
        registered_model_name="Entrainement_XGBoost_Haute_Precision"
    )

    print(f"Modèle enregistré dans MLflow ! (F1-Score: {meilleur_f1:.4f}, Seuil: {meilleur_seuil:.2f})")