import os
import urllib.parse
import streamlit as st
from langchain_community.utilities import SQLDatabase
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_ollama import ChatOllama

# Importer les fonctions RAG développées séparément
try:
    from rag_service import interroger_assistant, initialiser_base_vectorielle
    rag_module_ready = True
except ImportError:
    rag_module_ready = False


# ==========================================
# 1. CONFIGURATION DE LA PAGE & DESIGN
# ==========================================
st.set_page_config(
    page_title="Plateforme Anti-Fraude & Decision Support",
    page_icon="🛡️",
    layout="wide"
)

st.markdown("""
<style>
    .stChatMessage[data-testimonial="user"] {
        background-color: #004080 !important;
        color: white !important;
        border-radius: 12px;
    }
    .stChatMessage[data-testimonial="assistant"] {
        background-color: #f0f2f6 !important;
        color: #1f2937 !important;
        border-radius: 12px;
        border: 1px solid #e5e7eb;
    }
</style>
""", unsafe_allow_html=True)

st.title("🛡️ Plateforme Anti-Fraude & Copilot IA Global")
st.caption("Système intelligent de surveillance, d'analyse transactionnelle (SQL) et d'assistance documentaire (RAG).")


# ==========================================
# 2. INITIALISATION BDD, OLLAMA & AGENT SQL
# ==========================================
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@postgres:5432/memoire")

@st.cache_resource
def load_db_and_llm():
    db = SQLDatabase.from_uri(
        DATABASE_URL,
        include_tables=['bank_transactions_cleaned'],
        engine_args={"connect_args": {"client_encoding": "utf8"}}
    )
    llm = ChatOllama(
        model="llama3.2", 
        temperature=0,
        base_url="http://host.docker.internal:11434"
    )
    
    template = """En tant qu'expert PostgreSQL et anti-fraude, génère uniquement la requête SQL valide pour répondre à la question.

Schéma réel et complet de la table :
{schema}

Règles STRICTES de génération :
1. Inspecte ATTENTIVEMENT le schéma ci-dessus. N'utilise JAMAIS une colonne qui n'y figure pas.
2. Pour la RÉPARTITION PAR TYPE / CATÉGORIE / MARCHAND : Utilise la colonne textuelle appropriée du schéma, groupe par cette colonne (`GROUP BY`) et fais `SUM(is_fraud)`.
3. Pour la RÉPARTITION PAR MOIS : Extrais le mois du champ date/timestamp du schéma et fais `SUM(is_fraud)`.
4. Ne mets aucun texte autour, retourne UNIQUEMENT le code SQL brut.

Question : {question}
Requête SQL :"""
    
    prompt = PromptTemplate.from_template(template)
    
    chain = (
        {"schema": lambda _: db.get_table_info(), "question": lambda x: x["question"]}
        | prompt
        | llm
        | StrOutputParser()
    )
    
    return db, llm, chain

try:
    db, llm, sql_chain = load_db_and_llm()
    agent_ready = True
    st.sidebar.success("Connexion BDD & Ollama (Llama 3.2) OK")
except Exception as e:
    agent_ready = False
    st.sidebar.warning(f"Mode simulation BDD/Ollama : {e}")


# ==========================================
# 3. NAVIGATION MULTI-MODULES VIA ONGLETS
# ==========================================
tab_copilot, tab_rag, tab_alerts, tab_dg = st.tabs([
    "🤖 Copilot SQL (Analyst)",
    "📚 Assistant RAG (Règles & Rapports)",
    "🚨 Centre d'Alertes Sécurité",
    "📊 Vue Décisionnelle (DG)"
])


# ------------------------------------------
# MODULE 1 : COPILOT SQL (DONNÉES TRANSACTIONNELLES)
# ------------------------------------------
with tab_copilot:
    st.subheader("📊 Copilot Analytique (Text-to-SQL)")
    st.write("Interrogez la base de données PostgreSQL (`bank_transactions_cleaned`) en langage naturel.")

    if "messages_sql" not in st.session_state:
        st.session_state.messages_sql = [
            {"role": "assistant", "content": "Bonjour ! Posez-moi une question sur le volume de transactions ou le nombre de fraudes."}
        ]

    for msg in st.session_state.messages_sql:
        with st.chat_message(msg["role"]):
            st.write(msg["content"])

    if prompt := st.chat_input("Ex: Donne-moi le volume de fraudes dans la base", key="chat_sql"):
        st.session_state.messages_sql.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.write(prompt)

        with st.chat_message("assistant"):
            with st.spinner("Analyse et exécution SQL en cours..."):
                if agent_ready:
                    try:
                        sql_query = sql_chain.invoke({"question": prompt})
                        sql_query_clean = sql_query.replace("```sql", "").replace("```", "").strip()
                        db_res = db.run(sql_query_clean)

                        synthesis_prompt = f"""
Tu es un assistant analytique expert en détection de fraude.
L'utilisateur a posé la question : "{prompt}".
La requête SQL exécutée est : {sql_query_clean}
Le résultat brut de la base de données est : {db_res}

Rédige une réponse synthétique, professionnelle et concise en français.

Règles de rédaction STRICTES :
1. Sois ultra-concis et réponds directement avec les résultats sous forme de liste à puces.
2. Ne mets PAS de disclaimer de conclusion.
3. Formate les chiffres avec des espaces pour les milliers (ex: 1 445 566).
"""
                        response = llm.invoke(synthesis_prompt).content
                        
                        with st.expander("🔍 Requête SQL exécutée"):
                            st.code(sql_query_clean, language="sql")
                            st.caption(f"Résultat BDD : {db_res}")

                    except Exception as err:
                        response = f"⚠️ Erreur lors du traitement : {err}"
                else:
                    response = "[Mode Simulation] La connexion BDD/Ollama n'est pas active."

                st.write(response)
                st.session_state.messages_sql.append({"role": "assistant", "content": response})


# ------------------------------------------
# MODULE 2 : ASSISTANT RAG (DOCUMENTATION & RÈGLES)
# ------------------------------------------
with tab_rag:
    st.subheader("💬 Assistant RAG (Règles Métiers & Documentation)")
    st.caption("Posez des questions sur les règles d'audit, les seuils ou les rapports PDF/TXT du dossier `/rag_docs`.")

    if st.button("🔄 Ré-indexer la documentation (/rag_docs)"):
        if rag_module_ready:
            with st.spinner("Indexation vectorielle dans ChromaDB en cours..."):
                initialiser_base_vectorielle()
                st.success("Documentation indexée avec succès !")
        else:
            st.error("Le module `rag_service.py` n'a pas été trouvé.")

    if "messages_rag" not in st.session_state:
        st.session_state.messages_rag = [
            {"role": "assistant", "content": "Bonjour ! Posez une question sur les règles de gestion ou les procédures de blocage."}
        ]

    for msg in st.session_state.messages_rag:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    if prompt_rag := st.chat_input("Ex: Quelles sont les règles de blocage pour les opérations suspectes ?", key="chat_rag"):
        st.session_state.messages_rag.append({"role": "user", "content": prompt_rag})
        with st.chat_message("user"):
            st.markdown(prompt_rag)

        with st.chat_message("assistant"):
            with st.spinner("Recherche dans la documentation vectorisée..."):
                if rag_module_ready:
                    reponse = interroger_assistant(prompt_rag)
                else:
                    reponse = "[Simulation RAG] `rag_service.py` non disponible."
                
                st.markdown(reponse)
                st.session_state.messages_rag.append({"role": "assistant", "content": reponse})


# ------------------------------------------
# MODULE 3 : CENTRE D'ALERTES SÉCURITÉ
# ------------------------------------------
with tab_alerts:
    st.subheader("⚡ Flux de Transactions Suspectes (Temps Réel)")
    col_a, col_b = st.columns([3, 1])
    with col_a:
        st.error("🚨 **Alerte Critique (Score Risque XGBoost : 96.8%)**")
        st.write("**ID Transaction :** TX-984201 | **Montant :** 185 000 FCFA | **Heure :** 02:41 AM")
    with col_b:
        st.button("🔒 Bloquer la Carte", key="btn_block")
        st.button("✅ Approuver", key="btn_app")


# ------------------------------------------
# MODULE 4 : VUE DÉCISIONNELLE (DG)
# ------------------------------------------
with tab_dg:
    st.subheader("📈 Indicateurs Clés de Performance (KPIs)")
    kpi1, kpi2, kpi3 = st.columns(3)
    kpi1.metric("Total Transactions (Silver)", "7 477 306")
    kpi2.metric("Taux de Fraude Effectif", "19.97%", delta="-0.2%")
    kpi3.metric("Nombre de Fraudes Identifiées", "1 493 446")