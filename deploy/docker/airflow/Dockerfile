FROM apache/airflow:3.2.1

USER airflow

COPY airflow-requirements.txt /requirements.txt

RUN pip install --no-cache-dir -r /requirements.txt