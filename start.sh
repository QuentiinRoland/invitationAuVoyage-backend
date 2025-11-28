#!/bin/bash
set -e

echo "🔧 Running migrations..."
python manage.py migrate

echo "👤 Creating superuser..."
python create_superuser.py || echo "⚠️ Superuser creation failed, continuing..."

echo "🚀 Starting Gunicorn..."
exec gunicorn config.wsgi:application \
    --bind 0.0.0.0:${PORT:-8000} \
    --workers 2 \
    --timeout 120 \
    --log-level info \
    --access-logfile - \
    --error-logfile -

