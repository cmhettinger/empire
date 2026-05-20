.PHONY: empire-up empire-down empire-ps empire-logs

empire-up: ## Start the full Empire local stack
	$(COMPOSE) up -d postgres pgbouncer redis airflow-api airflow-scheduler airflow-dag-processor airflow-triggerer airflow-worker

empire-down: ## Stop the full Empire local stack
	$(COMPOSE) stop airflow-api airflow-scheduler airflow-dag-processor airflow-triggerer airflow-worker redis pgbouncer postgres

empire-ps: ## Show full Empire stack status
	$(COMPOSE) ps postgres pgbouncer redis airflow-api airflow-scheduler airflow-dag-processor airflow-triggerer airflow-worker

empire-logs: ## Tail full Empire stack logs
	$(COMPOSE) logs -f postgres pgbouncer redis airflow-api airflow-scheduler airflow-dag-processor airflow-triggerer airflow-worker