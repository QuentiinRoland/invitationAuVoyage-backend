#!/bin/bash
set -e
set -x
echo "🔧 Running migrations..."
python manage.py migrate --no-input
echo "👤 Creating superuser..."
python create_superuser.py || true
echo "🚀 Starting Gunicorn (NUCLEAR OPTION)..."
exec gunicorn config.wsgi:application --bind "0.0.0.0:${PORT:-8080}" --workers 2 --worker-class sync --log-level debug --access-logfile - --error-logfile - --timeout 120 --forwarded-allow-ips '*'
