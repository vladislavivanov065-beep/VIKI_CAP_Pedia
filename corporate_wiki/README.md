# Corporate Wiki

## Docker

```bash
cp .env.example .env
docker compose up --build
docker compose exec web python manage.py migrate
docker compose exec web python manage.py createsuperuser
docker compose exec web pytest
```

Приложение — `http://localhost:8000`.

## Без Docker

```bash
cp .env.example .env
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

## Миграции

```bash
python manage.py makemigrations
python manage.py migrate
```

## Администратор

```bash
python manage.py createsuperuser
```

```bash
python manage.py create_initial_admin
```

## Тесты

```bash
pytest
coverage run -m pytest
coverage report
```

## Статика

```bash
python manage.py collectstatic --noinput
```

## Production

```bash
DJANGO_SETTINGS_MODULE=config.settings.production gunicorn config.wsgi:application --bind 0.0.0.0:8000 --workers 1 --threads 4
```

## Резервное копирование

```bash
python manage.py backup_database
```
