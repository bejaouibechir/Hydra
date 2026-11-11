export AIRFLOW_HOME="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/airflow_home"
export AIRFLOW__CORE__DAGS_FOLDER="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/dags"
export AIRFLOW__CORE__LOAD_EXAMPLES=False
