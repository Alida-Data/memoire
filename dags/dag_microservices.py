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

    # 1. Extraction
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

    # 2. Transformation des données brutes
    task_transform = SimpleHttpOperator(
        task_id='appel_microservice_transform',
        http_conn_id='http_transform',
        endpoint='run', # Appelle l'endpoint de base du transform-service
        method='POST',
        data="{}",
        headers={"Content-Type": "application/json"},
        extra_options={"timeout": (60, None)}, 
        response_check=lambda response: response.status_code == 200,
    )

    # 3. Chargement vers PostgreSQL
    task_load = SimpleHttpOperator(
        task_id='appel_microservice_load',
        http_conn_id='http_load',
        endpoint='run',
        method='POST',
        data="{}",
        headers={"Content-Type": "application/json"},
        extra_options={"timeout": (60, None)},
        response_check=lambda response: response.status_code == 200,
    )

    # 4. Modélisation et Tracking MLOps (XGBoost + MLflow)
    task_train = SimpleHttpOperator(
        task_id='appel_microservice_train',
        http_conn_id='http_transform', # Même connexion car c'est le même conteneur
        endpoint='run-pipeline',       # Ton point d'accès pour XGBoost
        method='POST',
        data="{}",
        headers={"Content-Type": "application/json"},
        extra_options={"timeout": (60, None)}, 
        response_check=lambda response: response.status_code == 200,
    )

    # Enchaînement optimal de bout en bout
    task_extract >> task_transform >> task_load >> task_train