import os
import psycopg2

def get_db_connection():
    """Établit la connexion avec la base de données PostgreSQL (basée sur DBeaver)"""
    return psycopg2.connect(
        host=os.getenv("DB_HOST", "localhost"),
        database=os.getenv("DB_NAME", "memoire"),      # Mis à jour : "memoire" au lieu de "anti_fraude_db"
        user=os.getenv("DB_USER", "postgres"),
        password=os.getenv("DB_PASSWORD", "postgres"), # Remplacez par votre vrai mot de passe (ou utilisez une variable d'environnement)
        port=os.getenv("DB_PORT", "5433")        # Mis à jour : Port 5433 au lieu de 5432
    )
def executer_copilot_sql(prompt: str):
    """
    Exécute une requête sur PostgreSQL en fonction du prompt utilisateur 
    et retourne les colonnes et les lignes sous un format structuré.
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        prompt_lower = prompt.lower()
        
        # Logique de ciblage ou de génération SQL
        if "suspectes" in prompt_lower or "fraude" in prompt_lower:
            query = "SELECT transaction_id, customer_id, amount, merchant_category, timestamp, is_fraud FROM transactions WHERE is_fraud = true LIMIT 10;"
        elif "dernières transactions" in prompt_lower:
            query = "SELECT transaction_id, customer_id, amount, merchant_category, timestamp, is_fraud FROM transactions ORDER BY timestamp DESC LIMIT 10;"
        else:
            query = "SELECT transaction_id, customer_id, amount, merchant_category, timestamp, is_fraud FROM transactions LIMIT 10;"

        cursor.execute(query)
        
        # Récupération des noms de colonnes et des données
        columns = [desc[0] for desc in cursor.description]
        data = cursor.fetchall()

        cursor.close()
        conn.close()

        return {
            "type": "success",
            "columns": columns,
            "data": data
        }

    except Exception as e:
        return {
            "type": "error",
            "message": f"Erreur lors de l'exécution SQL : {str(e)}"
        }