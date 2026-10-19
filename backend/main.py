import json
import os
from datetime import date, datetime
from io import BytesIO

import mlflow
import mlflow.xgboost
import pandas as pd
import psycopg2
import decimal
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from google.cloud import storage
from pydantic import BaseModel
from psycopg2.extras import RealDictCursor

# Vos services personnalisés
import sql_copilot_service
from rag_service import ajouter_document, interroger_assistant, recherche_semantique, lister_documents, supprimer_document
from sql_copilot_service import get_db_connection

# Configuration MLflow alignée sur la base SQLite locale
MLFLOW_TRACKING_URI = os.getenv("MLFLOW_TRACKING_URI", "http://mlflow_proxy:5000")
mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)
mlflow.set_experiment("Fraud_Detection_Pipeline")

# Prompt Système strict pour forcer l'usage de 'bank_transactions_cleaned'
SYSTEM_PROMPT = """
Tu es un expert SQL spécialisé en PostgreSQL. Ton rôle est de convertir les questions en langage naturel des utilisateurs en requêtes SQL valides.

RÈGLES IMPORTANTES :
1. La table principale à utiliser pour toutes les requêtes de transaction s'appelle IMPÉRATIVEMENT : bank_transactions_cleaned
2. Ne génère JAMAIS de requêtes ciblant "transactions" ou "bank_transactions". Utilise TOUJOURS "bank_transactions_cleaned".
3. Ne retourne que la requête SQL brute, sans bloc de code Markdown explicatif.
"""

app = FastAPI(title="API Anti-Fraude & RAG 2.0", version="2.0")

# Autoriser les requêtes depuis l'interface React
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Config GCP Storage
GCS_BUCKET_NAME = os.getenv("GCP_BUCKET_NAME", "memoire-rag-docs-bucket")

try:
    storage_client = storage.Client()
except Exception:
    storage_client = None

# Table des alertes
try:
    _conn = get_db_connection()
    _cur = _conn.cursor()
    _cur.execute("""
        CREATE TABLE IF NOT EXISTS fraud_alerts (
            id SERIAL PRIMARY KEY,
            transaction_id TEXT,
            amount NUMERIC,
            decision TEXT,
            probability NUMERIC,
            is_fraud_real INTEGER,
            status TEXT DEFAULT 'À traiter',
            created_at TIMESTAMP DEFAULT NOW()
        );
    """)
    _conn.commit()
    _cur.close()
    _conn.close()
    print("[INFO] Table fraud_alerts prête.")
except Exception as e:
    print(f" Impossible de créer/vérifier la table fraud_alerts : {e}")

# Chargement du modèle XGBoost depuis le volume partagé
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PARENT_DIR = os.path.dirname(BASE_DIR)
ROOT_SHARED_DATA = os.path.join(PARENT_DIR, "shared_data")
LOCAL_SHARED_DATA = os.path.join(BASE_DIR, "shared_data")

# Priorité : Variable d'environnement > Racine du projet (/memoire) > Dossier backend
if os.getenv("SHARED_DATA_DIR"):
    SHARED_DATA_DIR = os.getenv("SHARED_DATA_DIR")
elif os.path.exists(ROOT_SHARED_DATA):
    SHARED_DATA_DIR = ROOT_SHARED_DATA
else:
    SHARED_DATA_DIR = LOCAL_SHARED_DATA

MODEL_PATH = os.path.join(SHARED_DATA_DIR, "fraud_model.json")
COLUMNS_PATH = os.path.join(SHARED_DATA_DIR, "model_columns.json")

fraud_model = None
MODEL_FEATURE_COLUMNS = []

try:
    import xgboost as xgb

    if not os.path.exists(MODEL_PATH) or not os.path.exists(COLUMNS_PATH):
        raise FileNotFoundError(
            f"{MODEL_PATH} ou {COLUMNS_PATH} introuvable."
        )

    fraud_model = xgb.XGBClassifier()
    fraud_model.load_model(MODEL_PATH)

    with open(COLUMNS_PATH) as f:
        MODEL_FEATURE_COLUMNS = json.load(f)

    print(f"[INFO] Modèle chargé depuis {MODEL_PATH} — {len(MODEL_FEATURE_COLUMNS)} colonnes.")

except Exception as e:
    print(f"⚠️ Impossible de charger le modèle : {e}")
    fraud_model = None
    MODEL_FEATURE_COLUMNS = []

# Seuil de décision optimal
THRESHOLD_PATH = os.path.join(SHARED_DATA_DIR, "threshold.json")
_default_threshold = 0.5
if os.path.exists(THRESHOLD_PATH):
    try:
        with open(THRESHOLD_PATH) as f:
            _default_threshold = json.load(f)["threshold"]
        print(f"[INFO] Seuil optimal chargé depuis {THRESHOLD_PATH} : {_default_threshold}")
    except Exception as e:
        print(f"⚠️ Impossible de lire {THRESHOLD_PATH} ({e}), seuil par défaut 0.5 utilisé.")
FRAUD_THRESHOLD = float(os.getenv("FRAUD_THRESHOLD", str(_default_threshold)))


# Modèles Pydantic
class QueryRequest(BaseModel):
    prompt: str
    user_role: str = "analyst"


class PredictFraudRequest(BaseModel):
    amount: float
    high_risk_merchant: int = 0
    transaction_hour: int = 12
    weekend_transaction: int = 0
    velocity_last_hour: int = 0
    card_present: int = 0
    merchant_type: str = "physical"
    card_type: str = "Basic Debit"
    device: str = "Chrome"
    channel: str = "web"
    country: str = "USA"
    city_size: str = "medium"
    currency: str = "USD"


class LoginRequest(BaseModel):
    username: str
    password: str


@app.get("/")
def read_root():
    return {"message": "Bienvenue sur l'API Anti-Fraude & RAG 2.0", "docs": "/docs"}


# Endpoint Copilot SQL
@app.post("/api/v1/copilot-sql")
def execute_sql_query(payload: QueryRequest):
    prompt_complet = f"{SYSTEM_PROMPT}\n\nQuestion utilisateur : {payload.prompt}"
    resultat_sql = sql_copilot_service.executer_copilot_sql(prompt_complet)

    return {
        "prompt": payload.prompt,
        "result": resultat_sql
    }


# Endpoint RAG Assistant
@app.post("/api/v1/rag-chat")
def chat_rag(payload: QueryRequest):
    try:
        reponse_rag = interroger_assistant(payload.prompt)
        return {"response": reponse_rag}
    except Exception as e:
        return {"response": f"Erreur RAG : {str(e)}"}


# Endpoint Téléversement GCP + Indexation RAG
@app.post("/api/v1/upload-doc")
async def upload_document_to_gcp(file: UploadFile = File(...), required_role: str = Form("analyst")):
    try:
        content = await file.read()

        if storage_client:
            bucket = storage_client.bucket(GCS_BUCKET_NAME)
            blob = bucket.blob(f"documents/{file.filename}")
            blob.upload_from_string(content, content_type=file.content_type)

        class UploadFileWrapper:
            def __init__(self, filename, file_obj):
                self.filename = filename
                self.file = file_obj

        wrapped_file = UploadFileWrapper(file.filename, BytesIO(content))
        ajouter_document(wrapped_file, required_role)

        return {
            "status": "success",
            "filename": file.filename,
            "gcs_uri": f"gs://{GCS_BUCKET_NAME}/documents/{file.filename}"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# Endpoint Liste des documents indexés par l'assistant
@app.get("/api/v1/documents")
def get_documents():
    try:
        return {"documents": lister_documents()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# Endpoint Retrait d'un document de l'assistant
@app.delete("/api/v1/documents/{filename}")
def delete_document(filename: str):
    try:
        removed = supprimer_document(filename)
        if not removed:
            raise HTTPException(status_code=404, detail=f"Document '{filename}' introuvable.")
        return {"status": "success", "filename": filename}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# Endpoint Statistiques du tableau de bord
@app.get("/api/v1/dashboard-stats")
def dashboard_stats():
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()

        cur.execute("""
            WITH bounds AS (
                SELECT MAX(timestamp) AS max_ts FROM bank_transactions_cleaned
            )
            SELECT
                (SELECT COUNT(*)
                 FROM bank_transactions_cleaned, bounds
                 WHERE timestamp >= bounds.max_ts - INTERVAL '24 hours') AS analyzed_count,

                (SELECT COUNT(*)
                 FROM bank_transactions_cleaned, bounds
                 WHERE is_fraud = 1
                   AND timestamp >= bounds.max_ts - INTERVAL '24 hours') AS open_alerts,

                (SELECT COALESCE(SUM(amount), 0)
                 FROM bank_transactions_cleaned, bounds
                 WHERE is_fraud = 1
                   AND timestamp >= bounds.max_ts - INTERVAL '24 hours') AS amount_at_risk;
        """)
        analyzed_count, open_alerts, amount_at_risk = cur.fetchone()
        cur.close()

        return {
            "analyzed_count": int(analyzed_count or 0),
            "open_alerts": int(open_alerts or 0),
            "amount_at_risk": float(amount_at_risk or 0),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if conn:
            conn.close()


# Endpoint KPI pour la section Indicateurs
@app.get("/api/v1/kpi-stats")
def get_kpi_stats():
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()

        cur.execute("""
            SELECT 
                COUNT(*) as total_transactions,
                SUM(CASE WHEN is_fraud = 1 THEN 1 ELSE 0 END) as total_frauds,
                ROUND(AVG(amount)::numeric, 2) as avg_amount,
                SUM(CASE WHEN is_fraud = 1 THEN amount ELSE 0 END) as total_fraud_amount
            FROM bank_transactions_cleaned;
        """)
        row = cur.fetchone()
        cur.close()

        total_tx = row[0] or 0
        total_frauds = row[1] or 0
        avg_amt = float(row[2]) if row[2] else 0.0
        fraud_amt = float(row[3]) if row[3] else 0.0
        fraud_rate = round((total_frauds / total_tx) * 100, 2) if total_tx > 0 else 0.0

        return {
            "total_transactions": total_tx,
            "total_frauds": total_frauds,
            "avg_amount": avg_amt,
            "total_fraud_amount": fraud_amt,
            "fraud_rate": fraud_rate
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if conn:
            conn.close()


# Endpoint Connexion
USERS_DB = {
    "analyste1": {"password": "changeme", "role": "analyst"},
    "direction1": {"password": "changeme", "role": "dg"},
    "admin1": {"password": "changeme", "role": "admin"},
}

@app.post("/api/v1/login")
def login(payload: LoginRequest):
    user = USERS_DB.get(payload.username)
    if not user or user["password"] != payload.password:
        raise HTTPException(status_code=401, detail="Identifiant ou mot de passe incorrect")
    return {"username": payload.username, "role": user["role"]}


# Fonction de scoring partagée
def score_transaction(raw_row: dict):
    if fraud_model is None or not MODEL_FEATURE_COLUMNS:
        raise RuntimeError("Modèle indisponible : échec du chargement depuis shared_data.")
    X_raw = pd.DataFrame([raw_row])
    X_encoded = pd.get_dummies(X_raw, drop_first=True)
    X_final = X_encoded.reindex(columns=MODEL_FEATURE_COLUMNS, fill_value=0)
    probability = float(fraud_model.predict_proba(X_final)[0, 1])
    decision = "FRAUDULEUSE" if probability >= FRAUD_THRESHOLD else "LÉGITIME"
    return decision, probability

@app.get("/api/v1/sample-transactions")
def sample_transactions(limit: int = 10):
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()

        cur.execute("""
            SELECT
                transaction_id, customer_id, amount, merchant_category, merchant_type,
                currency, country, city, city_size, card_type, card_present,
                device, channel, distance_from_home, high_risk_merchant,
                transaction_hour, weekend_transaction, timestamp, is_fraud
            FROM bank_transactions_cleaned
            ORDER BY timestamp DESC
            LIMIT %s;
        """, (limit,))

        cols = [desc[0] for desc in cur.description]
        rows = cur.fetchall()
        cur.close()

        transactions = []
        for r in rows:
            row = dict(zip(cols, r))

            for key, val in row.items():
                if isinstance(val, (datetime, date)):
                    row[key] = val.isoformat()
                elif isinstance(val, decimal.Decimal):
                    row[key] = float(val)
                elif val is None:
                    if key in ["amount", "distance_from_home"]:
                        row[key] = 0.0
                    elif key in ["card_present", "high_risk_merchant", "transaction_hour", "weekend_transaction", "is_fraud"]:
                        row[key] = 0
                    else:
                        row[key] = ""

            transactions.append(row)

        return {"transactions": transactions}

    except Exception as e:
        print(f"[ERREUR CRITIQUE sample-transactions] : {str(e)}")
        raise HTTPException(status_code=500, detail=f"Erreur SQL/Python : {str(e)}")

    finally:
        if conn:
            conn.close()

@app.get("/api/v1/copilot-kpis")
def get_copilot_kpis():
    """
    Alimente les cartes de statistiques du Copilot / Onglet Transactions 
    avec les données réelles de la table fraud_alerts.
    """
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()

        # Statistiques des alertes générées dans fraud_alerts
        cur.execute("""
            SELECT 
                COUNT(*) AS total_alertes, 
                COALESCE(SUM(amount), 0) AS montant_a_risque 
            FROM fraud_alerts;
        """)
        total_alertes, montant_a_risque = cur.fetchone()

        cur.close()

        return {
            "total_alertes": total_alertes,
            "montant_a_risque": float(montant_a_risque),
            "currency": "XOF"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if conn:
            conn.close()

# Endpoint Prédiction XGBoost
@app.post("/api/v1/predict-fraud")
def predict_fraud(payload: PredictFraudRequest):
    if fraud_model is None or not MODEL_FEATURE_COLUMNS:
        raise HTTPException(
            status_code=503,
            detail="Modèle indisponible : échec du chargement depuis shared_data."
        )
    try:
        raw_row = {
            "amount": payload.amount,
            "high_risk_merchant": int(payload.high_risk_merchant),
            "transaction_hour": int(payload.transaction_hour),
            "weekend_transaction": int(payload.weekend_transaction),
            "velocity_last_hour": int(payload.velocity_last_hour),
            "card_present": int(payload.card_present),
            "merchant_type": payload.merchant_type,
            "card_type": payload.card_type,
            "device": payload.device,
            "channel": payload.channel,
            "country": payload.country,
            "city_size": payload.city_size,
            "currency": payload.currency,
        }
        decision, probability = score_transaction(raw_row)
        return {"decision": decision, "probability": probability, "threshold": FRAUD_THRESHOLD}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# Surveillance en direct
@app.post("/api/v1/live-monitor/tick")
def live_monitor_tick(n: int = 5):
    if fraud_model is None or not MODEL_FEATURE_COLUMNS:
        raise HTTPException(status_code=503, detail="Modèle indisponible.")
    
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()

        cur.execute("""
            CREATE TABLE IF NOT EXISTS fraud_alerts (
                id SERIAL PRIMARY KEY,
                transaction_id VARCHAR(100),
                amount NUMERIC,
                decision VARCHAR(50),
                probability FLOAT,
                is_fraud_real INT,
                status VARCHAR(50) DEFAULT 'À traiter',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)

        cur.execute("""
            SELECT transaction_id, amount, high_risk_merchant, transaction_hour,
                   weekend_transaction, card_present, merchant_type, card_type,
                   device, channel, country, city_size, currency, is_fraud
            FROM bank_transactions_cleaned
            ORDER BY RANDOM()
            LIMIT %s;
        """, (n,))
        
        cols = [d[0] for d in cur.description]
        rows = cur.fetchall()

        results = []
        blocked = 0

        for r in rows:
            row = dict(zip(cols, r))

            def safe_int(val, default=0):
                if val is None:
                    return default
                try:
                    return int(val)
                except (ValueError, TypeError):
                    return default

            def safe_float(val, default=0.0):
                if val is None:
                    return default
                try:
                    return float(val)
                except (ValueError, TypeError):
                    return default

            raw_row = {
                "amount": safe_float(row.get("amount")),
                "high_risk_merchant": safe_int(row.get("high_risk_merchant")),
                "transaction_hour": safe_int(row.get("transaction_hour")),
                "weekend_transaction": safe_int(row.get("weekend_transaction")),
                "velocity_last_hour": 0,
                "card_present": safe_int(row.get("card_present")),
                "merchant_type": row.get("merchant_type") or "Unknown",
                "card_type": row.get("card_type") or "Unknown",
                "device": row.get("device") or "Unknown",
                "channel": row.get("channel") or "Unknown",
                "country": row.get("country") or "Unknown",
                "city_size": row.get("city_size") or "Unknown",
                "currency": row.get("currency") or "USD",
            }

            decision, probability = score_transaction(raw_row)
            is_fraud_real = safe_int(row.get("is_fraud"))

            if decision == "FRAUDULEUSE":
                blocked += 1
                cur.execute("""
                    INSERT INTO fraud_alerts
                        (transaction_id, amount, decision, probability, is_fraud_real, status)
                    VALUES (%s, %s, %s, %s, %s, 'À traiter');
                """, (
                    str(row.get("transaction_id", "")),
                    safe_float(row.get("amount")),
                    decision,
                    safe_float(probability),
                    is_fraud_real
                ))

            results.append({
                "transaction_id": row.get("transaction_id"),
                "amount": safe_float(row.get("amount")),
                "decision": decision,
                "probability": probability,
                "is_fraud_real": is_fraud_real,
            })

        conn.commit()
        cur.close()
        return {
            "processed": len(results),
            "blocked": blocked,
            "approved": len(results) - blocked,
            "results": results
        }

    except Exception as e:
        if conn:
            conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if conn:
            conn.close()

# @app.get("/api/v1/dashboard-kpis")
@app.get("/api/v1/dashboard-kpis")
def get_dashboard_kpis():
    """Alimente la carte 'Indicateurs Clés' avec les données réelles."""
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()

        # Totaux depuis la table nettoyée
        cur.execute("""
            SELECT 
                COUNT(*) AS total_tx,
                COALESCE(SUM(amount), 0) AS montant_total_tx
            FROM bank_transactions_cleaned;
        """)
        total_tx, montant_total_tx = cur.fetchone()

        # Fraudes réelles détectées
        cur.execute("""
            SELECT 
                COUNT(*) AS total_fraudes,
                COALESCE(SUM(amount), 0) AS montant_fraudes
            FROM bank_transactions_cleaned
            WHERE is_fraud = 1;
        """)
        total_fraudes, montant_fraudes = cur.fetchone()

        cur.close()

        taux_fraude = (total_fraudes / total_tx * 100) if total_tx > 0 else 0

        return {
            "total_transactions": total_tx,
            "fraudes_detectees": total_fraudes,
            "taux_fraude": round(taux_fraude, 2),
            "montant_total_tx": float(montant_total_tx),
            "montant_total_fraude": float(montant_fraudes),
            "currency": "XOF"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if conn:
            conn.close()


@app.get("/api/v1/alerts-24h")
def get_alerts_24h():
    """Alimente la carte 'Transactions analysées / Signalements'."""
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()

        cur.execute("""
            SELECT 
                COUNT(*) AS total_signalements,
                COALESCE(SUM(amount), 0) AS montant_surveille
            FROM fraud_alerts;
        """)
        total_signalements, montant_surveille = cur.fetchone()
        cur.close()

        return {
            "transactions_analysees": total_signalements,  # Alignement sur vos 1 801 alertes
            "signalements_ouverts": total_signalements,
            "montant_sous_surveillance": float(montant_surveille),
            "currency": "XOF"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if conn:
            conn.close()


# --- VOTRE CODE EXISTANT ---

@app.get("/api/v1/decision-indicators")
def get_decision_indicators():
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()

        # Fraudes par Canal
        cur.execute("""
            SELECT COALESCE(channel, 'Inconnu') AS name, COUNT(*) AS value
            FROM bank_transactions_cleaned
            WHERE is_fraud = 1
            GROUP BY channel;
        """)
        by_channel = [{"name": row[0], "value": int(row[1])} for row in cur.fetchall()]

        # Fraudes par Type de Marchand
        cur.execute("""
            SELECT COALESCE(merchant_type, 'Inconnu') AS name, COUNT(*) AS value
            FROM bank_transactions_cleaned
            WHERE is_fraud = 1
            GROUP BY merchant_type;
        """)
        by_merchant = [{"name": row[0], "value": int(row[1])} for row in cur.fetchall()]

        cur.close()
        return {
            "by_channel": by_channel,
            "by_merchant": by_merchant
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if conn:
            conn.close()


@app.get("/api/v1/alerts")
def get_alerts(limit: int = 20):
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            SELECT id, transaction_id, amount, decision, probability, is_fraud_real, status, created_at
            FROM fraud_alerts
            ORDER BY created_at DESC
            LIMIT %s;
        """, (limit,))
        cols = [d[0] for d in cur.description]
        rows = cur.fetchall()
        cur.close()

        alerts = []
        for r in rows:
            row = dict(zip(cols, r))

            row["amount"] = float(row["amount"]) if row["amount"] is not None else 0.0
            row["probability"] = float(row["probability"]) if row["probability"] is not None else 0.0

            created_at_val = row.get("created_at")
            if hasattr(created_at_val, "isoformat"):
                row["created_at"] = created_at_val.isoformat()
            elif created_at_val is not None:
                row["created_at"] = str(created_at_val)
            else:
                row["created_at"] = None

            alerts.append(row)
        return {"alerts": alerts}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if conn:
            conn.close()


@app.post("/api/v1/alerts/{alert_id}/resolve")
def resolve_alert(alert_id: int):
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("UPDATE fraud_alerts SET status = 'Traitée' WHERE id = %s;", (alert_id,))
        conn.commit()
        cur.close()
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if conn:
            conn.close()