from datetime import datetime
from airflow import DAG
from airflow.providers.http.operators.http import SimpleHttpOperator

default_args = {
    'owner': 'Alida_MIAGE',
    'start_date': datetime(2026, 1, 1),
}

with DAG(
    'pipeline_microservices_fraude',
    default_args=default_args,
    description='Orchestration du pipeline ETL et MLOps de détection de fraude via microservices',
    schedule_interval=None,
    catchup=False,
    tags=['fraude', 'miage', 'ppda'],
) as dag:

    # 1. EXTRACTION
    task_extract = SimpleHttpOperator(
        task_id='appel_microservice_extract',
        http_conn_id='http_extract',
        endpoint='run',
        method='POST',
        data="{}",
        headers={"Content-Type": "application/json"},
        extra_options={"timeout": 7200}, 
        response_check=lambda response: response.status_code == 200,
    )

    # 2. TRANSFORMATION (Nettoyage du CSV uniquement)
    task_transform = SimpleHttpOperator(
        task_id='appel_microservice_transform',
        http_conn_id='http_transform',
        endpoint='transform-only', # Endpoint dédié uniquement au nettoyage
        method='POST',
        data="{}",
        headers={"Content-Type": "application/json"},
        extra_options={"timeout": 3600}, 
        response_check=lambda response: response.status_code == 200,
    )

    # 3. CHARGEMENT (Vers PostgreSQL)
    task_load = SimpleHttpOperator(
        task_id='appel_microservice_load',
        http_conn_id='http_load',
        endpoint='run',
        method='POST',
        data="{}",
        headers={"Content-Type": "application/json"},
        extra_options={"timeout": 3600}, # Timeout de 1h ajusté pour le gros volume
        response_check=lambda response: response.status_code == 200,
    )

    # 4. ENTRAÎNEMENT & MLFLOW (Après le chargement dans la base)
    task_train = SimpleHttpOperator(
        task_id='appel_microservice_train',
        http_conn_id='http_transform', # Même connexion car c'est le même conteneur
        endpoint='train-only',         # Appelle uniquement la partie entraînement
        method='POST',
        data="{}",
        headers={"Content-Type": "application/json"},
        extra_options={"timeout": 3600}, # Porté à 1h (3600s) pour éviter un timeout XGBoost
        response_check=lambda response: response.status_code == 200,
    )

    # Ordre de dépendance des tâches
    task_extract >> task_transform >> task_load >> task_train