#!/bin/bash
set -e

echo "🔧 Running migrations..."
python manage.py migrate

echo "👤 Creating superuser..."
python create_superuser.py || echo "⚠️ Superuser creation failed, continuing..."

echo "🚀 Starting Gunicorn..."

# Clear any Railway-injected gunicorn config that might have placeholders
unset GUNICORN_CMD_ARGS
unset WEB_CONCURRENCY
unset WORKER_CLASS
unset WORKER_TMP_DIR

exec gunicorn config.wsgi:application \
    --bind 0.0.0.0:${PORT:-8000} \
    --workers 2 \
    --timeout 120 \
    --log-level info \
    --access-logfile - \
    --error-logfile -

