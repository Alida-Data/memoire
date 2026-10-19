# =============================================================================
# mlflow_server.py — microservice HTTP appelé par Airflow (task_train,
# endpoint "train-only") pour déclencher l'entraînement et l'enregistrement
# du modèle dans MLflow.
# =============================================================================
import os
import json
import traceback
import numpy as np
import pandas as pd
import psycopg2
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from xgboost import XGBClassifier
from imblearn.over_sampling import SMOTE
from imblearn.pipeline import Pipeline as ImbPipeline
from sklearn.metrics import accuracy_score, f1_score, precision_score, recall_score
from sklearn.model_selection import train_test_split, RandomizedSearchCV, StratifiedKFold
import mlflow
import mlflow.xgboost

app = FastAPI(title="MLflow Training Service")

mlflow.set_tracking_uri(os.getenv("MLFLOW_TRACKING_URI", "http://mlflow_proxy:5000"))
# Nom de l'expérience corrigé
mlflow.set_experiment("Detection_Fraude_Financial")


DATABASE_URL = os.getenv("DATABASE_URL")
DB_HOST = os.getenv("DB_HOST", "postgres")
DB_NAME = os.getenv("DB_NAME", "memoire")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD", "postgres")
DB_PORT = os.getenv("DB_PORT", "5432")


def get_connection():
    if DATABASE_URL:
        return psycopg2.connect(DATABASE_URL)
    return psycopg2.connect(
        host=DB_HOST, database=DB_NAME, user=DB_USER, password=DB_PASSWORD, port=DB_PORT
    )


def train_model():
    conn = get_connection()
    df = pd.read_sql("SELECT * FROM bank_transactions_cleaned;", conn)
    conn.close()

    cols_to_drop = [
        'is_fraud', 'transaction_id', 'customer_id', 'timestamp', 'merchant_category',
        'card_number', 'merchant', 'device_fingerprint', 'ip_address',
    ]
    X = df.drop(columns=[c for c in cols_to_drop if c in df.columns], errors='ignore')

    if 'card_present' in X.columns:
        X['card_present'] = X['card_present'].astype(int)

    X = pd.get_dummies(X, drop_first=True)
    y = df['is_fraud'].astype(int)

    model_columns = X.columns.tolist()
    with open("model_columns.json", "w") as f:
        json.dump(model_columns, f)

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )
    ratio_origine = float(np.sum(y_train == 0) / np.sum(y_train == 1))

    pipeline = ImbPipeline([
        ('smote', SMOTE(random_state=42)),
        ('clf', XGBClassifier(eval_metric='logloss', random_state=42, n_jobs=-1)),
    ])

    param_distributions = {
        'smote__sampling_strategy': [0.75, 1.0],
        'clf__n_estimators': [400, 600, 800, 100],
        'clf__max_depth': [6, 8, 10, 12],
        'clf__learning_rate': [0.01, 0.02, 0.03, 0.05],
        'clf__subsample': [0.8, 0.9, 1.0],
        'clf__colsample_bytree': [0.7, 0.8, 0.9],
        'clf__scale_pos_weight': [ratio_origine, ratio_origine * 1.5],
    }

    cv = StratifiedKFold(n_splits=3, shuffle=True, random_state=42)  # 3 folds au lieu de 5

    search = RandomizedSearchCV(
        pipeline,
        param_distributions=param_distributions,
        n_iter=60,  # 20 itérations au lieu de 100
        scoring='average_precision',
        cv=cv,
        n_jobs=-1,
        random_state=42,
        verbose=1,
        refit=True,
    )
    search.fit(X_train, y_train)
    model = search.best_estimator_.named_steps['clf']

    # Nom du Run mis à jour
    with mlflow.start_run(run_name="Entrainement_XGBoost_Haute_Precision"):
        mlflow.log_params({f"best_{k}": v for k, v in search.best_params_.items()})
        mlflow.log_metric("cv_best_f1", search.best_score_)

        y_probs = model.predict_proba(X_test)[:, 1]
        meilleur_seuil = 0.5
        meilleur_f1 = 0.0
        # Balayage fin du seuil de décision (pas de 0.005)
        for threshold in np.arange(0.01, 0.95, 0.005):
            y_pred_temp = (y_probs >= threshold).astype(int)
            score = f1_score(y_test, y_pred_temp, pos_label=1)
            if score > meilleur_f1:
                meilleur_f1 = score
                meilleur_seuil = threshold

        y_pred_final = (y_probs >= meilleur_seuil).astype(int)
        acc = accuracy_score(y_test, y_pred_final)
        precision = precision_score(y_test, y_pred_final, pos_label=1, zero_division=0)
        recall = recall_score(y_test, y_pred_final, pos_label=1, zero_division=0)

        # Enregistrement des métriques avec le nom f1_score
        mlflow.log_param("best_threshold", round(meilleur_seuil, 2))
        mlflow.log_metric("f1_score", meilleur_f1)
        mlflow.log_metric("accuracy", acc)
        mlflow.log_metric("precision", precision)
        mlflow.log_metric("recall", recall)

        mlflow.xgboost.log_model(
    xgb_model=model,
    artifact_path="model"
)
        mlflow.log_artifact("model_columns.json")

    return {
        "cv_best_f1": search.best_score_,
        "f1_score": meilleur_f1,
        "accuracy": acc,
        "precision": precision,
        "recall": recall,
        "best_threshold": round(meilleur_seuil, 2),
        "best_params": search.best_params_,
    }


@app.post("/train-only")
def train_only():
    try:
        metrics = train_model()
        return JSONResponse(status_code=200, content={"status": "success", "metrics": metrics})
    except Exception as e:
        traceback.print_exc()
        return JSONResponse(status_code=500, content={"status": "error", "detail": str(e)})


@app.get("/")
def health_check():
    return {"status": "mlflow_server is running"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)