import os
import urllib.parse
import streamlit as st
from langchain_community.utilities import SQLDatabase
from langchain_ollama import ChatOllama
from langchain.chains.sql_database.query import create_sql_query_chain

# ==========================================
# 1. CONFIGURATION DE LA PAGE & DESIGN
# ==========================================
st.set_page_config(
    page_title="Copilot Anti-Fraude & Decision Support",
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

st.title("🛡️ Plateforme Anti-Fraude & Copilot IA")
st.caption("Système intelligent de surveillance, d'alerte et d'analyse comportementale sur la couche Silver.")

# ==========================================
# 2. INITIALISATION BASE DE DONNÉES & OLLAMA
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
    chain = create_sql_query_chain(llm, db)
    return db, llm, chain

try:
    db, llm, sql_chain = load_db_and_llm()
    agent_ready = True
    st.sidebar.success("🟢 Connexion BDD & Ollama (Llama 3.2) OK")
except Exception as e:
    agent_ready = False
    st.sidebar.warning(f"⚠️ Mode démo : {e}")

# ==========================================
# 3. NAVIGATION MULTI-MODULES
# ==========================================
tab_copilot, tab_alerts, tab_dg = st.tabs([
    "🤖 Copilot IA (Analyst Assistant)",
    "🚨 Centre d'Alertes Sécurité",
    "📊 Vue Décisionnelle (DG)"
])

# ------------------------------------------
# MODULE 1 : COPILOT & ASSISTANT IA
# ------------------------------------------
with tab_copilot:
    st.subheader("💬 Assistant Conversationnel Analytique")
    st.write("Interrogez la base de données sur les flux de transactions.")

    if "messages" not in st.session_state:
        st.session_state.messages = [
            {"role": "assistant", "content": "Bonjour ! Je suis votre Copilot Anti-Fraude local. Comment puis-je vous aider aujourd'hui ?"}
        ]

    # Affichage de tous les messages de l'historique
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.write(msg["content"])

    # Champ de saisie utilisateur
    if prompt := st.chat_input("Ex: Donne-moi le volume de fraudes dans la base"):
        # Afficher le message utilisateur immédiatement
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.write(prompt)

        # Générer la réponse de l'assistant
        with st.chat_message("assistant"):
            with st.spinner("Analyse et exécution SQL en cours..."):
                if agent_ready:
                    try:
                        # 1. Génération de la requête SQL
                        sql_query = sql_chain.invoke({"question": prompt})
                        
                        # Nettoyage si le LLM entoure le code de balises markdown
                        sql_query_clean = sql_query.replace("```sql", "").replace("```", "").strip()
                        
                        # 2. Exécution directe dans la BDD PostgreSQL
                        db_res = db.run(sql_query_clean)
                        
                        # 3. Synthese en français avec le LLM
                        synthesis_prompt = f"""
Tu es un expert anti-fraude. 
L'utilisateur a posé la question : "{prompt}".
La requête SQL exécutée est : {sql_query_clean}
Le résultat brut de la base de données est : {db_res}

Rédige une réponse synthétique, professionnelle et claire en français pour répondre à la question.
"""
                        response = llm.invoke(synthesis_prompt).content
                        
                        # Affichage optionnel du SQL exécuté sous forme rétractable
                        with st.expander("🔍 Requête SQL exécutée"):
                            st.code(sql_query_clean, language="sql")
                            st.caption(f"Résultat BDD : {db_res}")

                    except Exception as err:
                        response = f"⚠️ Erreur lors du traitement : {err}"
                else:
                    response = "[Mode Simulation] La connexion BDD/Ollama n'est pas active."

                st.write(response)
                st.session_state.messages.append({"role": "assistant", "content": response})

# ------------------------------------------
# MODULE 2 : CENTRE D'ALERTES SÉCURITÉ
# ------------------------------------------
with tab_alerts:
    st.subheader("🚨 Flux de Transactions Suspectes (Temps Réel)")
    col_a, col_b = st.columns([3, 1])
    with col_a:
        st.error("🔴 **Alerte Critique (Score Risque XGBoost : 96.8%)**")
        st.write("**ID Transaction :** TX-984201 | **Montant :** 185 000 FCFA | **Heure :** 02:41 AM")
    with col_b:
        st.button("🚫 Bloquer la Carte", key="btn_block")
        st.button("✅ Approuver", key="btn_app")

# ------------------------------------------
# MODULE 3 : VUE DÉCISIONNELLE (DG)
# ------------------------------------------
with tab_dg:
    st.subheader("📈 Indicateurs Clés de Performance (KPIs)")
    kpi1, kpi2, kpi3 = st.columns(3)
    kpi1.metric("Total Transactions (Silver)", "7 477 306")
    kpi2.metric("Taux de Fraude Effectif", "19.97%", delta="-0.2%")
    kpi3.metric("Nombre de Fraudes Identifiées", "1 493 446")