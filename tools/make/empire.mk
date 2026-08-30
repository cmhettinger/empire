.PHONY: empire-up empire-up-latest empire-down empire-ps empire-logs empire-jellyfin-up empire-jellyfin-down empire-jellyfin-logs

EMPIRE_SERVICES := postgres pgbouncer redis airflow-api airflow-scheduler airflow-dag-processor airflow-triggerer airflow-worker

empire-up: ## Start the full Empire local stack using existing images
	$(COMPOSE) up -d --no-build $(EMPIRE_SERVICES)

empire-up-latest: airflow-build ## Refresh YouTube dependencies and start the full Empire local stack
	$(COMPOSE) up -d --no-build $(EMPIRE_SERVICES)

empire-down: ## Stop the full Empire local stack
	$(COMPOSE) stop jellyfin airflow-api airflow-scheduler airflow-dag-processor airflow-triggerer airflow-worker youtube-pot-provider redis pgbouncer postgres

empire-ps: ## Show full Empire stack status
	$(COMPOSE) ps postgres pgbouncer redis airflow-api airflow-scheduler airflow-dag-processor airflow-triggerer airflow-worker

empire-logs: ## Tail full Empire stack logs
	$(COMPOSE) logs -f postgres pgbouncer redis airflow-api airflow-scheduler airflow-dag-processor airflow-triggerer airflow-worker

empire-jellyfin-up: ## Start optional Empire Jellyfin service
	$(COMPOSE) --profile jellyfin up -d jellyfin

empire-jellyfin-down: ## Stop optional Empire Jellyfin service
	$(COMPOSE) stop jellyfin

empire-jellyfin-logs: ## Tail optional Empire Jellyfin logs
	$(COMPOSE) logs -f jellyfin
