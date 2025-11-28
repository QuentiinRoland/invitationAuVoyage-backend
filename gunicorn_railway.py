"""
Gunicorn configuration for Railway deployment
EXPLICITLY OVERRIDING CONFLICTING VARIABLES
"""
import os

# Server socket
port = os.getenv('PORT', '8080')
bind = f"0.0.0.0:{port}"

# Worker processes
workers = 2
worker_class = 'sync'
worker_connections = 1000
timeout = 120
keepalive = 5

# Logging
accesslog = '-'
errorlog = '-'
loglevel = 'debug'

# CRITICAL: EXPLICITLY SET HOOKS TO None
on_starting = None
on_reload = None
when_ready = None
pre_fork = None
post_fork = None
post_worker_init = None
worker_int = None
worker_abort = None
pre_exec = None
pre_request = None
post_request = None
child_exit = None
worker_exit = None
nworkers_changed = None
on_exit = None

# Server mechanics
daemon = False
pidfile = None
umask = 0
user = None
group = None
tmp_upload_dir = None

# Allow forwarded headers from proxy
forwarded_allow_ips = '*'
