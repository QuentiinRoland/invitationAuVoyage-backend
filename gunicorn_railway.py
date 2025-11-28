"""
Gunicorn configuration for Railway deployment
Targeted overrides for conflicting environment variables
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

# CRITICAL FIX: Only override the hooks that conflict with Railway Env Vars
# Railway seems to inject WORKER_INT="INT", causing Gunicorn to crash.
# We define a dummy function with correct signature (arity 1) to override it.

def dummy_worker_hook(worker):
    pass

# Only override these specific hooks causing issues
worker_int = dummy_worker_hook
worker_abort = dummy_worker_hook

# We leave other hooks (on_starting, on_reload, etc.) undefined
# so Gunicorn uses its defaults and doesn't complain about signatures.

# Server mechanics
daemon = False
pidfile = None
umask = 0
user = None
group = None
tmp_upload_dir = None

# Allow forwarded headers from proxy
forwarded_allow_ips = '*'
