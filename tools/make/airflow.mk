.PHONY: airflow-build airflow-init airflow-up airflow-down airflow-ps airflow-logs airflow-worker-logs airflow-api-logs airflow-dags airflow-dag-runs airflow-shell airflow-pip-freeze airflow-pip-list airflow-pip-show

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

airflow-dags: ## List Airflow DAGs
	$(COMPOSE) exec airflow-api airflow dags list

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