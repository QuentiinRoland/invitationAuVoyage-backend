"""Gunicorn configuration for Railway deployment"""
import os

# CRUCIAL: Railway injecte le port via la variable PORT
port = os.environ.get('PORT', '8080')
bind = f"0.0.0.0:{port}"

# Configuration minimale
workers = 2
worker_class = 'sync'
timeout = 120
keepalive = 5

# Logging pour debug
accesslog = '-'
errorlog = '-'
loglevel = 'info'
capture_output = True

# Configuration Railway
forwarded_allow_ips = '*'
secure_scheme_headers = {
    'X-FORWARDED-PROTOCOL': 'ssl',
    'X-FORWARDED-PROTO': 'https',
    'X-FORWARDED-SSL': 'on'
}

# Afficher le port au démarrage
print(f"🔌 Gunicorn configuré pour écouter sur 0.0.0.0:{port}")