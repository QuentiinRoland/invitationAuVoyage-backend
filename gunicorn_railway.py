"""
Gunicorn configuration for Railway deployment
EXPLICITLY OVERRIDING CONFLICTING VARIABLES WITH DUMMY FUNCTIONS
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

# CRITICAL: Define a dummy function to satisfy Gunicorn callable requirement
def dummy_hook(*args, **kwargs):
    pass

# Override all hooks with the dummy function
on_starting = dummy_hook
on_reload = dummy_hook
when_ready = dummy_hook
pre_fork = dummy_hook
post_fork = dummy_hook
post_worker_init = dummy_hook
worker_int = dummy_hook
worker_abort = dummy_hook
pre_exec = dummy_hook
pre_request = dummy_hook
post_request = dummy_hook
child_exit = dummy_hook
worker_exit = dummy_hook
nworkers_changed = dummy_hook
on_exit = dummy_hook

# Server mechanics
daemon = False
pidfile = None
umask = 0
user = None
group = None
tmp_upload_dir = None

# Allow forwarded headers from proxy
forwarded_allow_ips = '*'
