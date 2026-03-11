#!/bin/bash
export PKG_CONFIG_PATH="/opt/homebrew/lib/pkgconfig:$PKG_CONFIG_PATH"
export DYLD_LIBRARY_PATH="/opt/homebrew/lib:$DYLD_LIBRARY_PATH"
source venv/bin/activate
# Gunicorn avec timeout long (PDF + OpenAI peut prendre jusqu'à 120s) et threads pour éviter le blocage
gunicorn config.wsgi:application --bind 127.0.0.1:8003 --workers 2 --timeout 180 --worker-class sync --reload --log-level info
