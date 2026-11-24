# ==============================================================================
# OpenAQ Acquisition Pipeline - Makefile
# ==============================================================================

SHELL := /bin/bash
PYTHON ?= python3
YEAR ?= 2024
START ?= 2006
END ?= 2026

.PHONY: help install test dry-run acquire audit campaign clean

help:
	@echo "OpenAQ Acquisition Pipeline - Make Targets:"
	@echo "  make install             Provision environment, directories & systemd"
	@echo "  make test                Run automated unit test suite"
	@echo "  make dry-run YEAR=2024   Run pre-flight checks and manifest test without downloading"
	@echo "  make acquire YEAR=2024   Run interactive acquisition and integrity audit for target year"
	@echo "  make audit YEAR=2024     Run 5-stage integrity audit on existing year archive"
	@echo "  make campaign START=2020 END=2024  Sequentially acquire and audit a span of years"
	@echo "  make clean               Remove bytecode caches and temporary artifacts"

install:
	@chmod +x scripts/install.sh
	@./scripts/install.sh

test:
	@$(PYTHON) -m unittest discover tests

dry-run:
	@chmod +x bin/acquire_year.sh
	@./bin/acquire_year.sh $(YEAR) --dry-run

acquire:
	@chmod +x bin/acquire_year.sh
	@./bin/acquire_year.sh $(YEAR)

audit:
	@$(PYTHON) bin/audit_acquisition_integrity.py $(YEAR)

campaign:
	@chmod +x bin/acquire_campaign.sh
	@./bin/acquire_campaign.sh $(START) $(END)

clean:
	@find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	@find . -type f -name "*.pyc" -delete 2>/dev/null || true
