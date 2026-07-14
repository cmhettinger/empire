FROM apache/airflow:3.2.1

USER root

ARG DENO_VERSION=2.5.6
ARG TARGETARCH

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl ffmpeg unzip \
    && case "$TARGETARCH" in \
        amd64) DENO_ARCH="x86_64-unknown-linux-gnu" ;; \
        arm64) DENO_ARCH="aarch64-unknown-linux-gnu" ;; \
        *) echo "Unsupported TARGETARCH: $TARGETARCH" && exit 1 ;; \
    esac \
    && curl -fsSL "https://github.com/denoland/deno/releases/download/v${DENO_VERSION}/deno-${DENO_ARCH}.zip" -o /tmp/deno.zip \
    && unzip /tmp/deno.zip -d /usr/local/bin \
    && chmod +x /usr/local/bin/deno \
    && rm /tmp/deno.zip \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

USER airflow

COPY deploy/docker/airflow/airflow-requirements.txt /requirements.txt

RUN pip install --no-cache-dir -r /requirements.txt

COPY resources/branding /opt/empire/resources/branding

ENV EMPIRE_BRANDING_ROOT=/opt/empire/resources/branding

COPY packages/empire-mail /opt/empire/packages/empire-mail

RUN pip install --no-cache-dir /opt/empire/packages/empire-mail

COPY packages/empire-core /opt/empire/packages/empire-core

RUN pip install --no-cache-dir /opt/empire/packages/empire-core

COPY packages/empire-stonks-ohlcv /opt/empire/packages/empire-stonks-ohlcv

RUN pip install --no-cache-dir /opt/empire/packages/empire-stonks-ohlcv

COPY packages/empire-reports /opt/empire/packages/empire-reports

RUN pip install --no-cache-dir /opt/empire/packages/empire-reports

COPY packages/empire-youtube /opt/empire/packages/empire-youtube

RUN pip install --no-cache-dir /opt/empire/packages/empire-youtube

COPY packages/empire-weather /opt/empire/packages/empire-weather

RUN pip install --no-cache-dir /opt/empire/packages/empire-weather

COPY packages/empire-stonks-securities /opt/empire/packages/empire-stonks-securities

RUN pip install --no-cache-dir /opt/empire/packages/empire-stonks-securities
