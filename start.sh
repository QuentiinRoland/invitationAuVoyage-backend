#!/bin/bash
set -e
set -x

echo "🚀 STARTING APP SCRIPT..."

# NETTOYAGE CRITIQUE
echo "🧹 Cleaning environment variables..."
unset WORKER_INT
unset WORKER_ABORT
unset WORKER_EXIT
unset CHILD_EXIT
unset GUNICORN_CMD_ARGS

echo "🔧 Running migrations..."
python manage.py migrate --no-input

echo "👤 Creating superuser..."
python create_superuser.py || true

echo "🔥 STARTING GUNICORN..."
exec gunicorn config.wsgi:application \
    --bind "0.0.0.0:${PORT:-8080}" \
    --workers 2 \
    --worker-class sync \
    --log-level debug \
    --access-logfile - \
    --error-logfile - \
    --timeout 120 \
    --forwarded-allow-ips '*'
