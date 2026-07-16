import os
import pandas as pd
import psycopg2
from psycopg2 import extras
from fastapi import FastAPI, HTTPException
import uvicorn

class PostgresLoader:
    """Classe responsable du chargement massif de fichiers CSV volumineux dans PostgreSQL."""
    
    def __init__(self, db_url: str):
        self.db_url = db_url
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
        """Méthode interne pour mapper dynamiquement les types de colonnes du CSV."""
        schema = []
        for col in first_row_df.columns:
            if col == 'transaction_id':
                schema.append(f'"{col}" VARCHAR(255) PRIMARY KEY')
            elif col in ['amount', 'montant_brut', 'montant_transforme', 'velocity_last_hour', 'oldbalance_org', 'newbalance_orig', 'oldbalance_dest', 'newbalance_dest']:
                schema.append(f'"{col}" FLOAT')
            elif col in ['is_fraud', 'heure_transaction', 'jour_semaine', 'transaction_hour', 'high_risk_merchant', 'weekend_transaction', 'step', 'is_flagged_fraud']:
                schema.append(f'"{col}" INT')
            elif col in ['empreinte_sha256_64_caracteres', 'card_number']:
                schema.append(f'"{col}" VARCHAR(64)') 
            elif col in ['date_heure_proper', 'timestamp']:
                schema.append(f'"{col}" TIMESTAMP')
            else:
                # SÉCURITÉ ABSOLUE : Tout le reste passe en TEXT
                schema.append(f'"{col}" TEXT')
        return schema

    def prepare_table(self, file_path: str, table_name: str):
        """Supprime la table existante et recrée sa structure à partir du fichier source."""
        first_row = pd.read_csv(file_path, nrows=1)
        schema = self._generate_schema(first_row)
        
        # Le DROP TABLE garantit que l'espace disque est libéré à chaque exécution du DAG !
        self.cursor.execute(f"DROP TABLE IF EXISTS {table_name} CASCADE;")
        create_query = f"CREATE TABLE {table_name} ({', '.join(schema)});"
        self.cursor.execute(create_query)
        self.conn.commit()
        print(f"[INFO] Table {table_name} recréée avec succès.")

    def insert_data_by_chunks(self, file_path: str, table_name: str, chunk_size: int = 50000):
        """Lit le fichier CSV par paquets et injecte les données dans la table spécifiée."""
        print(f"[INFO] Insertion massive dans {table_name} par paquets de {chunk_size}...")
        
        for chunk in pd.read_csv(file_path, chunksize=chunk_size):
            
            # SÉCURITÉ : Supprimer la colonne parasite si elle est présente
            for col in chunk.columns:
                if chunk[col].astype(str).str.contains('num_transactions').any():
                    print(f"[WARNING] Colonne parasite détectée et supprimée : {col}")
                    chunk = chunk.drop(columns=[col])
            
            # Cast explicite des booléens/entiers
            cols_to_cast = ['high_risk_merchant', 'weekend_transaction', 'is_fraud']
            for col in cols_to_cast:
                if col in chunk.columns:
                    chunk[col] = chunk[col].astype(bool).astype(int)
            
            # Gestion des valeurs NaN/Null
            chunk = chunk.where(pd.notnull(chunk), None)
            
            # Reconstruction des colonnes et placeholders
            columns_list = list(chunk.columns)
            protected_cols = ",".join([f'"{c}"' for c in columns_list])
            values_placeholder = ",".join([f"%({c})s" for c in columns_list])
            
            # 💡 SÉCURITÉ CONFLICT : On n'applique le ON CONFLICT que si la clé primaire est présente dans ce CSV
            if 'transaction_id' in columns_list:
                conflict_clause = "ON CONFLICT (transaction_id) DO NOTHING"
            else:
                conflict_clause = ""

            query = f"""
                INSERT INTO {table_name} ({protected_cols}) 
                VALUES ({values_placeholder}) 
                {conflict_clause};
            """
            
            records = chunk.to_dict(orient='records')
            
            with self.conn.cursor() as page_cursor:
                extras.execute_batch(page_cursor, query, records, page_size=5000)
            
            self.conn.commit()

    def run_pipeline(self, file_path: str, table_name: str, chunk_size: int = 50000):
        """Orchestre le processus d'ingestion pour une table spécifique."""
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Le fichier {file_path} est introuvable.")

        try:
            self.connect()
            self.prepare_table(file_path, table_name)
            self.insert_data_by_chunks(file_path, table_name, chunk_size)
            print(f"[SUCCESS] Ingestion dans {table_name} terminée avec succès !")
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
RAW_DATA_PATH = os.getenv("RAW_DATA_PATH", "/data/raw_data.csv")
CLEAN_DATA_PATH = os.getenv("CLEAN_DATA_PATH", "/data/cleaned_data.csv")

db_loader = PostgresLoader(db_url=DATABASE_URL)

@app.post("/run")
def load():
    try:
        # 1. Chargement de la table brute (Bronze)
        print("[PROCESS] Lancement du chargement des données BRUTES...")
        db_loader.run_pipeline(
            file_path=RAW_DATA_PATH, 
            table_name="public.bank_transactions", 
            chunk_size=50000
        )
        
        # 2. Chargement de la table propre (Silver)
        print("[PROCESS] Lancement du chargement des données PROPRES...")
        db_loader.run_pipeline(
            file_path=CLEAN_DATA_PATH, 
            table_name="public.bank_transactions_cleaned", 
            chunk_size=50000
        )
        
        return {
            "status": "success", 
            "message": "Architecture Bronze & Silver déployée ! Données brutes et propres injectées avec succès."
        }
    except FileNotFoundError as fnf_e:
        raise HTTPException(status_code=404, detail=str(fnf_e))
    except Exception as e:
        print(f"[ERROR] Échec critique du microservice de chargement : {str(e)}")
        raise HTTPException(status_code=500, detail=f"Erreur interne au chargement : {str(e)}")


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)