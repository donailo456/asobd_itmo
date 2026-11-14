COMPOSE = docker compose --env-file .env.local

.PHONY: run stop gen load setup teardown
run:
	$(COMPOSE) up -d --build --wait

stop:
	$(COMPOSE) down

gen:
	python3 scripts/generate.py

load:
	python3 scripts/load.py

setup:
	$(COMPOSE) exec -T clickhouse clickhouse-client --multiquery < sql/schema.sql
	$(MAKE) gen
	$(MAKE) load

teardown:
	$(COMPOSE) exec -T clickhouse clickhouse-client --query 'DROP DATABASE IF EXISTS energosbyt SYNC'
