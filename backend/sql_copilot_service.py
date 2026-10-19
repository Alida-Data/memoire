import os
import psycopg2

def get_db_connection():
    """Établit la connexion avec la base de données PostgreSQL.

    Valeurs par défaut adaptées à main.py qui tourne DIRECTEMENT SUR
    WINDOWS (hors Docker) : 127.0.0.1:5433, le port que docker-compose.yml
    mappe vers le conteneur postgres_memoire ("ports: - 5433:5432").
    "postgres_memoire" et le port 5432 ne sont résolvables/accessibles que
    DEPUIS L'INTÉRIEUR du réseau Docker (ex. depuis transform-service) —
    jamais depuis un script lancé sur l'hôte.
    """
    return psycopg2.connect(
        host=os.getenv("POSTGRES_HOST", os.getenv("DB_HOST", "127.0.0.1")),
        database=os.getenv("POSTGRES_DB", os.getenv("DB_NAME", "memoire")),
        user=os.getenv("POSTGRES_USER", os.getenv("DB_USER", "postgres")),
        password=os.getenv("POSTGRES_PASSWORD", os.getenv("DB_PASSWORD", "postgres")),
        port=os.getenv("POSTGRES_PORT", os.getenv("DB_PORT", "5433"))
    )

def executer_copilot_sql(prompt_ou_query: str):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        prompt_lower = prompt_ou_query.lower()

        # Requêtes prédéfinies ou générées
        if "nombre total" in prompt_lower or "count" in prompt_lower:
            query = "SELECT COUNT(*) AS total_transactions FROM bank_transactions_cleaned;"
        elif "suspectes" in prompt_lower or "fraude" in prompt_lower:
            # Remplacement strict de true/false par 1/0
            query = "SELECT transaction_id, customer_id, amount, merchant_category, timestamp, is_fraud FROM bank_transactions_cleaned WHERE is_fraud = 1 LIMIT 10;"
        elif "dernières" in prompt_lower:
            query = "SELECT transaction_id, customer_id, amount, merchant_category, timestamp, is_fraud FROM bank_transactions_cleaned ORDER BY timestamp DESC LIMIT 10;"
        else:
            query = "SELECT transaction_id, customer_id, amount, merchant_category, timestamp, is_fraud FROM bank_transactions_cleaned LIMIT 10;"

        cursor.execute(query)
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
