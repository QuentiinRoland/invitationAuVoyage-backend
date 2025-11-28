#!/bin/bash
set -e
set -x

echo "🚀 STARTING APP SCRIPT..."

# NETTOYAGE AU CAS OÙ
unset WORKER_INT
unset WORKER_ABORT
unset GUNICORN_CMD_ARGS

echo "🔧 Running migrations..."
python manage.py migrate --no-input

echo "👤 Creating superuser..."
python create_superuser.py || true

echo "🔥 STARTING GUNICORN WITH SAFE CONFIG..."
exec gunicorn config.wsgi:application -c gunicorn_railway.py
