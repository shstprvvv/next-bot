SHELL := /bin/bash

COMPOSE ?= docker-compose
API_URL ?= http://localhost:8080

.PHONY: run up down build restart status health logs logs-api logs-bot deploy

run:
	python3 main.py

up:
	$(COMPOSE) up -d

down:
	$(COMPOSE) down

build:
	$(COMPOSE) up -d --build

restart:
	$(COMPOSE) restart

status:
	$(COMPOSE) ps

health:
	curl -fsS $(API_URL)/health

logs:
	$(COMPOSE) logs -f

logs-api:
	$(COMPOSE) logs -f api

logs-bot:
	$(COMPOSE) logs -f bot

deploy:
	bash scripts/deploy.sh