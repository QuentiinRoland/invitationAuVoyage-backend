# Configuration Gunicorn pour production sur Render

import multiprocessing
import os

# Configuration de base
bind = f"0.0.0.0:{os.getenv('PORT', '8000')}"
workers = 2  # Render Free tier a des limites de RAM
worker_class = "sync"
worker_connections = 1000
timeout = 60  # Timeout plus long pour les tâches lourdes (génération PDF)
keepalive = 2
max_requests = 1000
max_requests_jitter = 100
preload_app = True

# Configuration des logs (stdout/stderr sur Render)
accesslog = "-"  # Log vers stdout
errorlog = "-"   # Log vers stderr
loglevel = "info"
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" %(D)s'

# Configuration de sécurité
limit_request_line = 4094
limit_request_fields = 100
limit_request_field_size = 8190

# Configuration de la mémoire
worker_tmp_dir = "/dev/shm"

# Configuration des signaux
graceful_timeout = 30

# Configuration du proxy (important pour Render)
forwarded_allow_ips = "*"
secure_scheme_headers = {
    'X-FORWARDED-PROTOCOL': 'ssl',
    'X-FORWARDED-PROTO': 'https',
    'X-FORWARDED-SSL': 'on'
}


