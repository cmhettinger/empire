.PHONY: db-up db-down db-ps db-logs db-migrate db-info db-validate db-clean db-psql db-data-remediation

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

db-repair: ## Repair Flyway
	$(COMPOSE) run --rm flyway repair

db-psql: ## Open psql against Postgres
	$(COMPOSE) exec postgres sh -c 'psql -U "$$POSTGRES_USER" -d "$$POSTGRES_DB"'

db-data-remediation: ## Apply an opt-in data remediation (REMEDIATION=db/data-remediations/...sql)
	@test -n "$(REMEDIATION)" || (echo "ERROR: Set REMEDIATION=db/data-remediations/...sql" >&2; exit 1)
	bin/run-data-remediation --file "$(REMEDIATION)" --env-file deploy/env/$(DEPLOY_ENV).env --apply
