FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DJANGO_SETTINGS_MODULE=config.settings.production

WORKDIR /app

# libjpeg/zlib are needed by Pillow to decode/encode the image formats we
# accept (JPEG, PNG, WebP, GIF).
RUN apt-get update \
    && apt-get install -y --no-install-recommends libjpeg62-turbo zlib1g \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml /app/
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir .

COPY . /app/
# Strip any CRLF line endings a Windows checkout may have introduced —
# a carriage return right after "#!/bin/sh" makes the kernel look for a
# literal "/bin/sh\r" interpreter and fail with "no such file or directory".
RUN sed -i 's/\r$//' /app/entrypoint.sh \
    && chmod +x /app/entrypoint.sh

RUN mkdir -p /app/data /app/staticfiles

EXPOSE 8000

ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "1", "--threads", "4"]
