.PHONY: help

help: ## Show available commands
	@awk 'BEGIN {FS = ":.*##"; printf "\nEmpire targets:\n\n"} \
		/^[a-zA-Z0-9_.-]+:.*##/ {printf "  %-28s %s\n", $$1, $$2} \
	' $(MAKEFILE_LIST)