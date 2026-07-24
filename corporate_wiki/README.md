# Corporate Wiki

## Docker

```bash
cp .env.example .env
# указать ADMIN_USERNAME и ADMIN_TEMP_PASSWORD в .env
docker compose up --build
```

При старте контейнер автоматически применяет миграции, собирает
статику и создаёт первого администратора с логином/паролем из
`ADMIN_USERNAME`/`ADMIN_TEMP_PASSWORD` — если суперпользователь уже
есть, этот шаг пропускается (безопасно при перезапуске контейнера).

Приложение — `http://localhost:8000`.

```bash
docker compose exec web pytest
```

### Публикация через ngrok / другой туннель

Без этого Django ответит `400 Bad Request` на все запросы, включая
главную страницу — узнать домен, выданный ngrok, и указать его в `.env`
**до** запуска `docker compose up`:

```bash
DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1,.ngrok-free.app
DJANGO_CSRF_TRUSTED_ORIGINS=https://*.ngrok-free.app
```

(`.ngrok-free.app` — маска поддомена, переживает смену адреса при
каждом перезапуске ngrok; если ngrok выдал домен на другом суффиксе,
подставьте его). После изменения `.env` перезапустите контейнер:

```bash
docker compose up -d --build
```

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

## Поиск и рекомендации

Выполняются автоматически при старте контейнера (Docker); вручную или по
расписанию (например, через cron) — при запуске без Docker или для
пересборки после массового импорта статей.

```bash
python manage.py rebuild_search_index
python manage.py rebuild_similarity_cache
```
