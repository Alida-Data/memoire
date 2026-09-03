import os
from io import BytesIO
import psycopg2
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from google.cloud import storage

# Vos services personnalisés
import sql_copilot_service
from rag_service import ajouter_document, recherche_semantique, interroger_assistant

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

# Config PostgreSQL (mêmes variables que le script d'entraînement du modèle)
DB_HOST = os.getenv("DB_HOST", "127.0.0.1")
DB_NAME = os.getenv("DB_NAME", "memoire")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD", "postgres")
DB_PORT = os.getenv("DB_PORT", "5433")


def get_connection():
    return psycopg2.connect(
        host=DB_HOST,
        database=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD,
        port=DB_PORT,
    )


try:
    storage_client = storage.Client()
except Exception:
    storage_client = None

class QueryRequest(BaseModel):
    prompt: str
    user_role: str = "analyst"

@app.get("/")
def read_root():
    return {"message": "Bienvenue sur l'API Anti-Fraude & RAG 2.0", "docs": "/docs"}

# Endpoint Copilot SQL
@app.post("/api/v1/copilot-sql")
def execute_sql_query(payload: QueryRequest):
    """Exécute une requête SQL intelligente sur la base PostgreSQL via le module de service"""
    # Transmission du prompt utilisateur accompagné du SYSTEM_PROMPT strict
    prompt_complet = f"{SYSTEM_PROMPT}\n\nQuestion utilisateur : {payload.prompt}"

    resultat_sql = sql_copilot_service.executer_copilot_sql(prompt_complet)

    return {
        "prompt": payload.prompt,
        "result": resultat_sql
    }

## Endpoint RAG Assistant : Réponse textuelle via ChromaDB / LLM
@app.post("/api/v1/rag-chat")
def chat_rag(payload: QueryRequest):
    try:
        # Appel direct au RAG (ChromaDB + LLM) sans passer par sql_copilot_service
        reponse_rag = interroger_assistant(payload.prompt)
        return {"response": reponse_rag}
    except Exception as e:
        return {"response": f"Erreur RAG : {str(e)}"}

# Endpoint Téléversement et Sauvegarde GCP + Indexation RAG
@app.post("/api/v1/upload-doc")
async def upload_document_to_gcp(file: UploadFile = File(...), required_role: str = Form("analyst")):
    try:
        content = await file.read()

        # 1. Sauvegarde sur Google Cloud Storage (GCS)
        if storage_client:
            bucket = storage_client.bucket(GCS_BUCKET_NAME)
            blob = bucket.blob(f"documents/{file.filename}")
            blob.upload_from_string(content, content_type=file.content_type)

        # 2. Sauvegarde locale et indexation ChromaDB
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

# Endpoint Statistiques du tableau de bord (cartes "Transactions analysées",
# "Signalements ouverts", "Montant sous surveillance")
@app.get("/api/v1/dashboard-stats")
def dashboard_stats():
    conn = None
    try:
        conn = get_connection()
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
