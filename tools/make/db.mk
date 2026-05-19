.PHONY: db-up db-down db-ps db-logs db-migrate db-info db-validate db-clean db-psql

db-up: ## Start postgres and pgbouncer
	$(COMPOSE) up -d postgres pgbouncer

db-down: ## Stop database services
	$(COMPOSE) down

db-ps: ## Show running database containers
	$(COMPOSE) ps

db-logs: ## Tail postgres and pgbouncer logs
	$(COMPOSE) logs -f postgres pgbouncer

db-migrate: ## Run Flyway migrations
	$(COMPOSE) run --rm flyway migrate

db-info: ## Show Flyway migration info
	$(COMPOSE) run --rm flyway info

db-validate: ## Validate Flyway migrations
	$(COMPOSE) run --rm flyway validate

db-clean: ## Drop all objects in Flyway schemas
	$(COMPOSE) run --rm flyway clean

db-psql: ## Open psql against Postgres
	$(COMPOSE) exec postgres sh -c 'psql -U "$$POSTGRES_USER" -d "$$POSTGRES_DB"'