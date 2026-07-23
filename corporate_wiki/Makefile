.PHONY: install run migrate test lint format typecheck check docker-up docker-down

install:
	pip install -e ".[dev]"

run:
	python manage.py runserver

migrate:
	python manage.py migrate

test:
	pytest

lint:
	ruff check .

format:
	black .
	ruff check --fix .

typecheck:
	mypy .

check:
	python manage.py check

docker-up:
	docker compose up --build

docker-down:
	docker compose down
