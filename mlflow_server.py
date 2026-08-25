import xgboost as xgb
from sklearn.metrics import accuracy_score, f1_score, precision_score, recall_score
from sklearn.model_selection import train_test_split
import pandas as pd
from sklearn.model_selection import train_test_split
import mlflow
import mlflow.xgboost
import pandas as pd

# 1. Connexion au serveur MLflow local (port 5000)
mlflow.set_tracking_uri("http://localhost:5000")
mlflow.set_experiment("Detection Fraude Financial")

# 2. Chargement de vos données (adaptez selon votre source, ex: CSV ou PostgreSQL)
# df = pd.read_csv("votre_dataset_transactions.csv")
# X = df.drop(columns=['is_fraud'])
# y = df['is_fraud']

# X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42, stratify=y)

with mlflow.start_run(run_name="Run_XGBoost_Ultra_Optimise"):
    
    # 3. Définition des hyperparamètres poussés pour maximiser la performance
    params = {
        'n_estimators': 800,           # Grand nombre d'arbres pour capturer un maximum de détails
        'max_depth': 8,                # Profondeur élevée pour les cas complexes
        'learning_rate': 0.01,         # Apprentissage progressif très fin
        'subsample': 0.9,              # Échantillonnage des lignes
        'colsample_bytree': 0.9,       # Échantillonnage des colonnes
        'scale_pos_weight': 10,        # Ajusté pour pénaliser loupé de fraude (déséquilibre des classes)
        'eval_metric': 'logloss',
        'random_state': 42
    }
    
    # Log des hyperparamètres dans MLflow
    mlflow.log_params(params)
    
    # 4. Initialisation et entraînement du modèle XGBoost
    model = xgb.XGBClassifier(**params)
    model.fit(X_train, y_train)
    
    # 5. Prédictions et calcul des métriques
    y_pred = model.predict(X_test)
    
    acc = accuracy_score(y_test, y_pred)
    f1 = f1_score(y_test, y_pred, average='weighted')
    precision = precision_score(y_test, y_pred, zero_division=0)
    recall = recall_score(y_test, y_pred, zero_division=0)
    
    print(f"Accuracy obtenue : {acc * 100:.2f}%")
    print(f"F1-Score obtenu : {f1:.4f}")
    
    # 6. Enregistrement des métriques dans MLflow
    mlflow.log_metric("accuracy", acc)
    mlflow.log_metric("f1_score", f1)
    mlflow.log_metric("precision", precision)
    mlflow.log_metric("recall", recall)
    
    # 7. Sauvegarde du modèle dans le registre MLflow sous le nom souhaité
    mlflow.xgboost.log_model(
        xgb_model=model,
        artifact_path="model",
        registered_model_name="Entrainement_XGBoost_Haute_Precision"
    )
    
    print("Modèle entraîné et enregistré avec succès dans MLflow !")