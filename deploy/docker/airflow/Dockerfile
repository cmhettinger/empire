FROM apache/airflow:3.2.1

USER airflow

COPY deploy/docker/airflow/airflow-requirements.txt /requirements.txt

RUN pip install --no-cache-dir -r /requirements.txt

COPY packages/empire-mail /opt/empire/packages/empire-mail

RUN pip install --no-cache-dir /opt/empire/packages/empire-mail
