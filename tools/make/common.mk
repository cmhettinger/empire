DEPLOY_ENV ?= local

COMPOSE = docker compose \
	--env-file deploy/env/$(DEPLOY_ENV).env \
	-f deploy/compose/empire.yml