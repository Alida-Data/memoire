import os
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from google.cloud import storage

# Vos services personnalisés
import sql_copilot_service  # Ou database_copilot si vous avez renommé le fichier
from rag_service import ajouter_document, recherche_semantique, interroger_assistant

app = FastAPI(title="API Anti-Fraude & RAG 2.0", version="2.0")

# Autoriser les requêtes depuis l'interface React
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Config GCP Storage (Sécurisé pour éviter les crashs si pas de credentials locaux)
GCS_BUCKET_NAME = os.getenv("GCP_BUCKET_NAME", "memoire-rag-docs-bucket")
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

# Endpoint Copilot SQL (Connecté à votre vraie base PostgreSQL)
@app.post("/api/v1/copilot-sql")
def execute_sql_query(payload: QueryRequest):
    """Exécute une requête SQL intelligente sur la base PostgreSQL via le module de service"""
    resultat_sql = sql_copilot_service.executer_copilot_sql(payload.prompt)
    return {
        "prompt": payload.prompt,
        "result": resultat_sql
    }

# Endpoint RAG Assistant (Routeur intelligent entre SQL et RAG textuel)
@app.post("/api/v1/rag-chat")
def chat_rag(payload: QueryRequest):
    """
    Routeur intelligent : si la question concerne les transactions/chiffres, 
    on interroge le SQL, sinon on interroge le RAG textuel (ChromaDB).
    """
    texte_lower = payload.prompt.lower()
    mots_cles_sql = ["transaction", "montant", "fraude", "client", "combien", "carte", "chiffre"]
    
    if any(mot in texte_lower for mot in mots_cles_sql):
        # Redirection vers la base PostgreSQL
        reponse_sql = sql_copilot_service.executer_copilot_sql(payload.prompt)
        return {"response": f"Données récupérées de la base PostgreSQL :\n{reponse_sql}"}
    else:
        # Redirection vers l'assistant RAG documentaire
        reponse_rag = interroger_assistant(payload.prompt)
        return {"response": reponse_rag}

# Endpoint Téléversement et Sauvegarde GCP + Indexation RAG
@app.post("/api/v1/upload-doc")
async def upload_document_to_gcp(file: UploadFile = File(...), required_role: str = Form("analyst")):
    try:
        content = await file.read()
        
        # 1. Sauvegarde sur Google Cloud Storage (GCS) si le client est dispo
        if storage_client:
            bucket = storage_client.bucket(GCS_BUCKET_NAME)
            blob = bucket.blob(f"documents/{file.filename}")
            blob.upload_from_string(content, content_type=file.content_type)
        
        # 2. Sauvegarde locale et indexation dans la base vectorielle (ChromaDB via rag_service)
        # Note : On simule l'objet fichier pour la fonction d'ajout existante de rag_service
        from io import BytesIO
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