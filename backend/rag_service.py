import os
import shutil
from langchain_community.document_loaders import DirectoryLoader, TextLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import Chroma
from langchain_community.embeddings import FastEmbedEmbeddings  # Solution légère et rapide
from langchain_community.llms import Ollama  # Ou passe par une clé API (Mistral, Cohere, OpenAI)

# 1. Emplacements
DOCS_DIR = "./rag_docs"
CHROMA_DIR = "./chroma_db"

def initialiser_base_vectorielle():
    """Ingestion des documents du dossier /rag_docs"""
    if not os.path.exists(DOCS_DIR):
        os.makedirs(DOCS_DIR)
        
    loader = DirectoryLoader(DOCS_DIR, glob="**/*.txt", loader_cls=TextLoader)
    documents = loader.load()
    
    if not documents:
        return None

    # Découpage du texte en segments
    text_splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=50)
    chunks = text_splitter.split_documents(documents)

    # Embeddings et stockage vectoriel
    embeddings = FastEmbedEmbeddings()
    vectorstore = Chroma.from_documents(
        documents=chunks,
        embedding=embeddings,
        persist_directory=CHROMA_DIR
    )
    return vectorstore

def interroger_assistant(question: str):
    """Recherche contextuelle et génération de réponse"""
    embeddings = FastEmbedEmbeddings()
    
    # Chargement du Vector Store existant
    if os.path.exists(CHROMA_DIR):
        vectorstore = Chroma(persist_directory=CHROMA_DIR, embedding_function=embeddings)
    else:
        vectorstore = initialiser_base_vectorielle()
        if not vectorstore:
            return "Aucun document trouvé dans le dossier `rag_docs` pour alimenter l'assistant."

    # Recherche des 3 passages les plus pertinents
    docs_pertinents = vectorstore.similarity_search(question, k=3)
    contexte = "\n\n".join([doc.page_content for doc in docs_pertinents])

    # Construction du prompt avec contexte
    prompt = f"""Tu es un assistant expert en détection de fraude. 
Aide-toi du contexte suivant pour répondre à la question.

Contexte:
{contexte}

Question: {question}
Réponse:"""

    # Envoi au LLM (Exemple avec un modèle local Ollama ou fallback)
    try:
        llm = Ollama(model="mistral")
        return llm.invoke(prompt)
    except Exception:
        # Fallback si le LLM n'est pas joignable (synthèse brute du contexte)
        return f"**Contexte trouvé dans la documentation :**\n\n{contexte}"

def ajouter_document(uploaded_file, required_role: str = "analyst") -> str:
    """Reçoit un fichier téléchargé via l'API, l'enregistre dans /rag_docs et ré-initialise la base."""
    if not os.path.exists(DOCS_DIR):
        os.makedirs(DOCS_DIR)
        
    file_path = os.path.join(DOCS_DIR, uploaded_file.filename)
    
    # Enregistrement du fichier localement
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(uploaded_file.file, buffer)
        
    # Ré-indexation automatique de la base vectorielle avec le nouveau document
    initialiser_base_vectorielle()
    
    return file_path

def recherche_semantique(question: str):
    """Effectue une recherche sémantique simple (utilisée en interne si besoin)."""
    embeddings = FastEmbedEmbeddings()
    if os.path.exists(CHROMA_DIR):
        vectorstore = Chroma(persist_directory=CHROMA_DIR, embedding_function=embeddings)
        docs_pertinents = vectorstore.similarity_search(question, k=3)
        return docs_pertinents
    return []