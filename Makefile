.DEFAULT_GOAL := help

SHELL := bash
.SHELLFLAGS := -euo pipefail -c

include $(wildcard tools/make/*.mk)