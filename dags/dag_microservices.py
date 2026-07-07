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

    # 1. Appel au Microservice d'Extraction
    task_extract = SimpleHttpOperator(
        task_id='appel_microservice_extract',
        http_conn_id='http_extract',
        endpoint='run',
        method='POST',
        data="{}",
        headers={"Content-Type": "application/json"},
        extra_options={"timeout": (60, None)}, 
        response_check=lambda response: response.status_code == 200,
    )

    # 2. Appel au Microservice de Transformation
    task_transform = SimpleHttpOperator(
        task_id='appel_microservice_transform',
        http_conn_id='http_transform',
        endpoint='run', # Modifié si ton microservice de transformation de données a un endpoint 'run'
        method='POST',
        data="{}",
        headers={"Content-Type": "application/json"},
        extra_options={"timeout": (60, None)}, 
        response_check=lambda response: response.status_code == 200,
    )

    # 3. Appel au Microservice de Chargement (Ingestion vers Postgres)
    task_load = SimpleHttpOperator(
        task_id='appel_microservice_load',
        http_conn_id='http_load',
        endpoint='run',
        method='POST',
        data="{}",
        headers={"Content-Type": "application/json"},
        extra_options={"timeout": (60, None)}, # Sécurité timeout ajoutée vu les 30 min de traitement
        response_check=lambda response: response.status_code == 200,
    )

    # 4. Fin de chaîne : Appel au Microservice de Modélisation IA (XGBoost + MLflow)
    task_train = SimpleHttpOperator(
        task_id='appel_microservice_train',
        http_conn_id='http_transform', # Pointe sur le microservice de modélisation
        endpoint='run-pipeline',       # Ton endpoint d'entraînement XGBoost
        method='POST',
        data="{}",
        headers={"Content-Type": "application/json"},
        extra_options={"timeout": (60, None)}, # Laisse le temps au modèle de converger (150k lignes)
        response_check=lambda response: response.status_code == 200,
    )

    # Enchaînement séquentiel optimal de l'ingestion jusqu'au tracking MLOps
    task_extract >> task_transform >> task_load >> task_train