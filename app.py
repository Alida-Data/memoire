import os
import urllib.parse
import streamlit as st
from langchain_community.utilities import SQLDatabase
from langchain_community.agent_toolkits import create_sql_agent
from langchain_openai import ChatOpenAI

# ==========================================
# 1. CONFIGURATION DE LA PAGE & DESIGN
# ==========================================
st.set_page_config(
    page_title="Copilot Anti-Fraude & Decision Support",
    page_icon="🛡️",
    layout="wide"
)

# Style CSS pour personnaliser l'interface (bulles de chat et cartes)
st.markdown("""
<style>
    /* Style de la zone de chat */
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
    /* Cartes de métriques */
    .metric-card {
        background-color: #ffffff;
        padding: 15px;
        border-radius: 10px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.05);
        border-left: 4px solid #004080;
    }
</style>
""", unsafe_allow_html=True)

st.title("🛡️ Plateforme Anti-Fraude & Copilot IA")
st.caption("Système intelligent de surveillance, d'alerte et d'analyse comportementale sur la couche Silver.")

# ==========================================
# 2. INITIALISATION DE L'AGENT LANGCHAIN
# ==========================================
# Lecture de la variable d'environnement transmise par Docker Compose
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@postgres:5432/memoire")

@st.cache_resource
def load_sql_agent():
    # Connexion sécurisée avec encodage client UTF-8
    db = SQLDatabase.from_uri(
        DATABASE_URL,
        include_tables=['bank_transactions_cleaned'],
        engine_args={
            "connect_args": {"client_encoding": "utf8"}
        }
    )
    
    # Modèle LLM
    llm = ChatOpenAI(temperature=0, model="gpt-4o-mini")
    
    # Création du moteur Text-to-SQL
    agent = create_sql_agent(
        llm=llm,
        db=db,
        verbose=False,
        agent_type="openai-tools"
    )
    return agent

# Tentative de chargement de l'agent
try:
    copilot_agent = load_sql_agent()
    agent_ready = True
except Exception as e:
    agent_ready = False
    st.sidebar.warning(f"⚠️ Mode démo : Connexion BDD non établie ({e})")

# ==========================================
# 3. NAVIGATION MULTI-MODULES (ONGLETS)
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
    st.write("Interrogez la base de données ou demandez des synthèses sur les flux de transactions.")

    # Historique de discussion
    if "messages" not in st.session_state:
        st.session_state.messages = [
            {"role": "assistant", "content": "Bonjour ! Je suis votre Copilot Anti-Fraude. Comment puis-je vous aider dans votre analyse aujourd'hui ?"}
        ]

    # Affichage des messages
    for msg in st.session_state.messages:
        st.chat_message(msg["role"]).write(msg["content"])

    # Entrée utilisateur
    if prompt := st.chat_input("Ex: Donne-moi le volume de fraudes aujourd'hui ou le taux par tranche horaire."):
        st.session_state.messages.append({"role": "user", "content": prompt})
        st.chat_message("user").write(prompt)

        with st.spinner("Analyse des requêtes SQL et réflexion de l'IA..."):
            if agent_ready:
                try:
                    # Utilisation de .invoke() au lieu de .run() (nouvelle norme LangChain)
                    query_text = f"Tu es un expert anti-fraude bancaire. Réponds de manière claire et structurée en français. Question: {prompt}"
                    result = copilot_agent.invoke({"input": query_text})
                    response = result.get("output", str(result))
                except Exception as err:
                    response = f"Erreur lors de l'exécution : {err}"
            else:
                response = f"[Mode Simulation] Vous avez demandé : '{prompt}'. Connectez PostgreSQL pour obtenir le résultat réel de la table."

        st.session_state.messages.append({"role": "assistant", "content": response})
        st.chat_message("assistant").write(response)

# ------------------------------------------
# MODULE 2 : CENTRE D'ALERTES SÉCURITÉ
# ------------------------------------------
with tab_alerts:
    st.subheader("🚨 Flux de Transactions Suspectes (Temps Réel)")
    st.caption("Transactions bloquées ou nécessitant une confirmation de l'analyste.")
    
    col_a, col_b = st.columns([3, 1])
    with col_a:
        st.error("🔴 **Alerte Critique (Score Risque XGBoost : 96.8%)**")
        st.write("**ID Transaction :** TX-984201 | **Montant :** 185 000 FCFA | **Heure :** 02:41 AM")
        st.write("**Raison :** Pic de montant anormal à une heure nocturne récurrente pour la classe de risque.")
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