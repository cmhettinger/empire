.PHONY: airflow-build airflow-init airflow-up airflow-down airflow-ps airflow-logs airflow-worker-logs airflow-api-logs airflow-dags airflow-dag-history airflow-dag-runs airflow-shell airflow-pip-freeze airflow-pip-list airflow-pip-show

airflow-build: ## Build Empire Airflow image
	$(COMPOSE) build airflow-init

airflow-init: ## Initialize or migrate Airflow metadata DB
	$(COMPOSE) run --rm airflow-init

airflow-up: ## Start Airflow Celery stack
	$(COMPOSE) up -d redis airflow-api airflow-scheduler airflow-dag-processor airflow-triggerer airflow-worker

airflow-down: ## Stop Airflow services
	$(COMPOSE) stop airflow-api airflow-scheduler airflow-dag-processor airflow-triggerer airflow-worker redis

airflow-ps: ## Show Airflow containers
	$(COMPOSE) ps redis airflow-api airflow-scheduler airflow-dag-processor airflow-triggerer airflow-worker

airflow-logs: ## Tail Airflow logs
	$(COMPOSE) logs -f airflow-api airflow-scheduler airflow-dag-processor airflow-triggerer airflow-worker

airflow-api-logs: ## Tail Airflow API logs
	$(COMPOSE) logs -f airflow-api

airflow-worker-logs: ## Tail Airflow worker logs
	$(COMPOSE) logs -f airflow-worker

airflow-recreate: ## Recreate Airflow containers after image/dependency changes
	$(COMPOSE) up -d --force-recreate airflow-api airflow-scheduler airflow-dag-processor airflow-triggerer airflow-worker

airflow-dags: ## List current Airflow DAGs with latest version numbers
	@$(COMPOSE) exec airflow-api python -c 'from airflow.settings import Session; from sqlalchemy import text; s = Session(); rows = s.execute(text("with latest as (select dag_id, max(version_number) as version_number from dag_version group by dag_id) select d.dag_id, v.version_number, d.fileloc, d.is_paused, v.bundle_name, v.bundle_version from dag d join latest l on l.dag_id = d.dag_id join dag_version v on v.dag_id = l.dag_id and v.version_number = l.version_number order by d.dag_id")).fetchall(); s.close(); headers = ("dag_id", "version", "fileloc", "is_paused", "bundle_name", "bundle_version"); data = [tuple("" if value is None else str(value) for value in row) for row in rows]; widths = [len(header) for header in headers]; [widths.__setitem__(i, max(widths[i], len(row[i]))) for row in data for i in range(len(headers))]; fmt = " | ".join("{:<" + str(width) + "}" for width in widths); print(fmt.format(*headers)); print("-+-".join("-" * width for width in widths)); [print(fmt.format(*row)) for row in data]'

airflow-dag-history: ## List Airflow DAG version history
	@$(COMPOSE) exec airflow-api python -c 'from airflow.settings import Session; from sqlalchemy import text; s = Session(); rows = s.execute(text("select d.dag_id, v.version_number, d.fileloc, d.is_paused, v.bundle_name, v.bundle_version from dag d join dag_version v on v.dag_id = d.dag_id order by d.dag_id, v.version_number")).fetchall(); s.close(); headers = ("dag_id", "version", "fileloc", "is_paused", "bundle_name", "bundle_version"); data = [tuple("" if value is None else str(value) for value in row) for row in rows]; widths = [len(header) for header in headers]; [widths.__setitem__(i, max(widths[i], len(row[i]))) for row in data for i in range(len(headers))]; fmt = " | ".join("{:<" + str(width) + "}" for width in widths); print(fmt.format(*headers)); print("-+-".join("-" * width for width in widths)); [print(fmt.format(*row)) for row in data]'

airflow-dag-runs: ## List DAG runs (DAG=<dag_id>)
	$(COMPOSE) exec airflow-api airflow dags list-runs $(DAG)

airflow-shell: ## Open shell in Airflow API container
	$(COMPOSE) exec airflow-api bash

airflow-pip-freeze: ## Show installed Python packages in Airflow
	$(COMPOSE) exec airflow-api python -m pip freeze | sort

airflow-pip-list: ## Show installed Python packages (table)
	$(COMPOSE) exec airflow-api python -m pip list

airflow-pip-show: ## Show package details (PKG=<package>)
	@if [ -z "$(PKG)" ]; then \
		echo "Usage: make airflow-pip-show PKG=<package>"; \
		exit 1; \
	fi
	$(COMPOSE) exec airflow-api python -m pip show $(PKG)
