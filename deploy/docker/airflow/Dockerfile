FROM apache/airflow:3.2.1

USER airflow

COPY deploy/docker/airflow/airflow-requirements.txt /requirements.txt

RUN pip install --no-cache-dir -r /requirements.txt

COPY packages/empire-mail /opt/empire/packages/empire-mail

RUN pip install --no-cache-dir /opt/empire/packages/empire-mail

COPY packages/empire-core /opt/empire/packages/empire-core

RUN pip install --no-cache-dir /opt/empire/packages/empire-core

COPY packages/empire-youtube /opt/empire/packages/empire-youtube

RUN pip install --no-cache-dir /opt/empire/packages/empire-youtube
