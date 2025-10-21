# Configuration Gunicorn pour production sur Hetzner

import multiprocessing
import os

# Configuration de base
bind = "127.0.0.1:8000"
workers = multiprocessing.cpu_count() * 2 + 1
worker_class = "sync"
worker_connections = 1000
timeout = 30
keepalive = 2
max_requests = 1000
max_requests_jitter = 100
preload_app = True

# Configuration des logs
accesslog = "/var/log/invitationauvoyage/access.log"
errorlog = "/var/log/invitationauvoyage/error.log"
loglevel = "info"
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" %(D)s'

# Configuration de sécurité
limit_request_line = 4094
limit_request_fields = 100
limit_request_field_size = 8190

# Configuration des processus
user = "invitationauvoyage"
group = "invitationauvoyage"

# Configuration de la mémoire
worker_tmp_dir = "/dev/shm"

# Configuration des signaux
graceful_timeout = 30
worker_int = "INT"
worker_abort = "ABRT"

# Configuration du proxy
forwarded_allow_ips = "*"
secure_scheme_headers = {
    'X-FORWARDED-PROTOCOL': 'ssl',
    'X-FORWARDED-PROTO': 'https',
    'X-FORWARDED-SSL': 'on'
}

