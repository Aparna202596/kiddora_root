#!/bin/bash
set -e

echo ">>> Collecting static files..."
python manage.py collectstatic --noinput

echo ">>> Running migrations..."
python manage.py migrate --noinput

echo ">>> Starting Gunicorn (optimized per trainer)..."
exec gunicorn kiddora.wsgi:application \
    --bind 0.0.0.0:8000 \
    --workers 4 \
    --threads 2 \
    --max-requests 1000 \
    --max-requests-jitter 100 \
    --timeout 30 \
    --keep-alive 2 \
    --access-logfile - \
    --error-logfile -