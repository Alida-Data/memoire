import os
import pandas as pd
from sqlalchemy import create_engine

# Utilisation explicite du port 5433
DATABASE_URL = os.getenv(
    "DATABASE_URL", 
    "postgresql://postgres:postgres@localhost:5433/memoire"
)

def export_data_for_powerbi():
    print("🔄 Connexion à PostgreSQL sur localhost:5433...")
    engine = create_engine(DATABASE_URL)
    
    # Extraction depuis la table nettoyée
    query = "SELECT * FROM bank_transactions_cleaned;"
    print("📥 Extraction des données anonymisées...")
    df = pd.read_sql(query, engine)
    
    # Création du dossier d'exportation
    os.makedirs("data_export", exist_ok=True)
    
    # Génération du fichier CSV pour Power BI
    csv_path = "data_export/powerbi_fraud_data.csv"
    df.to_csv(csv_path, index=False, encoding="utf-8-sig")
    print(f"✅ Export CSV réussi : {csv_path} ({len(df)} lignes)")

if __name__ == "__main__":
    export_data_for_powerbi()