FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    TELEGRAM_SESSION_DIR=/data

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN groupadd --system --gid 10001 inbox \
    && useradd --system --uid 10001 --gid inbox --no-create-home inbox \
    && mkdir -p /data \
    && chown inbox:inbox /data

USER inbox

EXPOSE 8080
CMD ["sh", "-c", "umask 077; exec gunicorn --bind 0.0.0.0:8080 wsgi:app"]
