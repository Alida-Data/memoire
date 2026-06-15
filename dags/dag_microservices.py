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
    description='Orchestration du pipeline ETL de détection de fraude via microservices',
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
        response_check=lambda response: response.status_code == 200,
    )

    # 2. Appel au Microservice de Transformation (Appelle le code FastAPI)
    task_transform = SimpleHttpOperator(
        task_id='appel_microservice_transform',
        http_conn_id='http_transform',
        endpoint='run-pipeline',
        method='POST',
        data="{}",
        headers={"Content-Type": "application/json"},
        extra_options={"timeout": 3600}, # Évite le timeout pendant l'entraînement du Random Forest
        response_check=lambda response: response.status_code == 200,
    )

    # 3. Appel au Microservice de Chargement
    task_load = SimpleHttpOperator(
        task_id='appel_microservice_load',
        http_conn_id='http_load',
        endpoint='run',
        method='POST',
        data="{}",
        headers={"Content-Type": "application/json"},
        response_check=lambda response: response.status_code == 200,
    )

    # Enchaînement séquentiel du pipeline
    task_extract >> task_transform >> task_load