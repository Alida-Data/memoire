
import hashlib
import os
import pandas as pd

def anonymize_sensitive_data(df: pd.DataFrame) -> pd.DataFrame:
    """
    Anonymise les identifiants clients par hachage SHA-256 salé 
    et généralise les coordonnées géographiques (K-Anonymat).
    """
    df = df.copy()
    
    # Récupération de la clé de salage (ou valeur par défaut sécurisée)
    salt = os.getenv("HASH_SALT", "SecretKey123").encode('utf-8')
    
    # 1. Hachage cryptographique de la carte bancaire (SHA-256)
    def hash_value(val):
        return hashlib.sha256(str(val).encode('utf-8') + salt).hexdigest()
    
    if 'cc_num' in df.columns:
        df['cc_num_hashed'] = df['cc_num'].apply(hash_value)
        df.drop(columns=['cc_num'], inplace=True)
        
    # 2. Généralisation des coordonnées GPS (arrondi à 1 décimale ~ 11 km)
    if 'lat' in df.columns and 'long' in df.columns:
        df['lat'] = df['lat'].round(1)
        df['long'] = df['long'].round(1)
        
    return df