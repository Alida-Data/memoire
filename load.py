import os
import pandas as pd
import psycopg2
from psycopg2 import extras
from fastapi import FastAPI, HTTPException
import uvicorn

class PostgresLoader:
    """Classe responsable du chargement massif de fichiers CSV volumineux dans PostgreSQL."""
    
    def __init__(self, db_url: str, table_name: str = "public.bank_transactions_cleaned"):
        self.db_url = db_url
        self.table_name = table_name
        self.conn = None
        self.cursor = None

    def connect(self):
        """Établit la connexion à la base de données PostgreSQL."""
        print("[INFO] Connexion à PostgreSQL...")
        self.conn = psycopg2.connect(self.db_url)
        self.cursor = self.conn.cursor()

    def disconnect(self):
        """Ferme proprement le curseur et la connexion."""
        if self.cursor:
            self.cursor.close()
        if self.conn:
            self.conn.close()
        print("[INFO] Connexion PostgreSQL fermée.")

    def _generate_schema(self, first_row_df: pd.DataFrame) -> list:
        """Méthode interne pour mapper dynamiquement les types de colonnes du CSV nettoyé."""
        schema = []
        for col in first_row_df.columns:
            if col == 'transaction_id':
                schema.append(f'"{col}" VARCHAR(255) PRIMARY KEY')
            elif col in ['amount', 'montant_brut', 'montant_transforme', 'velocity_last_hour']:
                schema.append(f'"{col}" FLOAT')
            elif col in ['is_fraud', 'heure_transaction', 'jour_semaine', 'transaction_hour', 'high_risk_merchant', 'weekend_transaction']:
                schema.append(f'"{col}" INT')
            elif col in ['empreinte_sha256_64_caracteres', 'card_number']:
                schema.append(f'"{col}" VARCHAR(64)') 
            elif col in ['date_heure_proper', 'timestamp']:
                schema.append(f'"{col}" TIMESTAMP')
            else:
                # 🟢 SÉCURITÉ ABSOLUE : Tout le reste (dont les chaînes JSON/Dictionnaires) passe en TEXT
                schema.append(f'"{col}" TEXT')
        return schema

    def prepare_table(self, file_path: str):
        """Supprime la table nettoyée existante et recrée sa structure à partir du fichier source."""
        first_row = pd.read_csv(file_path, nrows=1)
        schema = self._generate_schema(first_row)
        
        # Recréation de la table dédiée aux données propres
        self.cursor.execute(f"DROP TABLE IF EXISTS {self.table_name} CASCADE;")
        create_query = f"CREATE TABLE {self.table_name} ({', '.join(schema)});"
        self.cursor.execute(create_query)
        self.conn.commit()
        print(f"[INFO] Table {self.table_name} recréée avec succès (Clé Primaire activée).")

    def insert_data_by_chunks(self, file_path: str, chunk_size: int = 50000):
        """Lit le fichier CSV par paquets et injecte les données avec un mapping par clés nommé."""
        print(f"[INFO] Insertion massive des lignes par paquets de {chunk_size}...")
        
        for chunk in pd.read_csv(file_path, chunksize=chunk_size):
            
            # 🟢 SÉCURITÉ EXTRAORDINAIRE : Identifier et supprimer la colonne parasite contenant le dictionnaire
            # On cherche s'il y a une colonne qui commence par des accolades ou du texte de dictionnaire
            for col in chunk.columns:
                # Si une ligne contient '{'num_transactions'', on dégage la colonne du traitement
                if chunk[col].astype(str).str.contains('num_transactions').any():
                    print(f"[WARNING] Colonne parasite détectée et supprimée pour éviter le crash : {col}")
                    chunk = chunk.drop(columns=[col])
            
            # 1. Cast explicite des colonnes problématiques en entiers (0/1)
            cols_to_cast = ['high_risk_merchant', 'weekend_transaction', 'is_fraud']
            for col in cols_to_cast:
                if col in chunk.columns:
                    chunk[col] = chunk[col].astype(bool).astype(int)
            
            # 2. Gestion des valeurs NaN/Null
            chunk = chunk.where(pd.notnull(chunk), None)
            
            # 3. Récupération stricte de la liste des colonnes du DataFrame restantes
            columns_list = list(chunk.columns)
            protected_cols = ",".join([f'"{c}"' for c in columns_list])
            
            # 4. Préparation de la requête nommée dynamique
            values_placeholder = ",".join([f"%({c})s" for c in columns_list])
            
            query = f"""
                INSERT INTO {self.table_name} ({protected_cols}) 
                VALUES ({values_placeholder}) 
                ON CONFLICT (transaction_id) DO NOTHING;
            """
            
            # 5. Conversion en dictionnaire pour forcer l'alignement par clé
            records = chunk.to_dict(orient='records')
            
            # 6. Injection robuste
            with self.conn.cursor() as page_cursor:
                extras.execute_batch(page_cursor, query, records, page_size=5000)
            
            self.conn.commit()

    def run_pipeline(self, file_path: str, chunk_size: int = 50000):
        """Orchestre la totalité du processus d'ingestion (Load)."""
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Le fichier {file_path} est introuvable.")

        try:
            self.connect()
            self.prepare_table(file_path)
            self.insert_data_by_chunks(file_path, chunk_size)
            print("[SUCCESS] Ingestion terminée avec succès !")
        except Exception as e:
            if self.conn:
                self.conn.rollback()
            raise e
        finally:
            self.disconnect()


# =====================================================================
# Configuration et initialisation du microservice FastAPI
# =====================================================================

app = FastAPI(title="Load Microservice")

DATABASE_URL = os.getenv(
    "DATABASE_URL", 
    "postgresql://postgres:postgres@postgres_memoire:5432/memoire"
)
CLEAN_DATA_PATH = os.getenv("CLEAN_DATA_PATH", "/data/cleaned_data.csv")

db_loader = PostgresLoader(
    db_url=DATABASE_URL,
    table_name="public.bank_transactions_cleaned"
)

@app.post("/run")
def load():
    try:
        db_loader.run_pipeline(file_path=CLEAN_DATA_PATH, chunk_size=50000)
        return {
            "status": "success", 
            "message": "Les données nettoyées et dédupliquées ont été injectées avec succès !"
        }
    except FileNotFoundError as fnf_e:
        raise HTTPException(status_code=404, detail=str(fnf_e))
    except Exception as e:
        print(f"[ERROR] Échec critique du microservice de chargement : {str(e)}")
        raise HTTPException(status_code=500, detail=f"Erreur interne au chargement : {str(e)}")


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)