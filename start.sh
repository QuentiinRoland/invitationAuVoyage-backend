#!/bin/bash
set -e

echo "🔧 Running migrations..."
python manage.py migrate

echo "👤 Creating superuser..."
python create_superuser.py || echo "⚠️ Superuser creation failed, continuing..."

echo "🚀 Starting Gunicorn..."

# Use our own config file to override any Railway-injected settings
exec gunicorn config.wsgi:application --config gunicorn_railway.py

