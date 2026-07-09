import multiprocessing
import os

bind = f"0.0.0.0:{os.environ.get('PORT', '10000')}"
workers = int(os.environ.get("WEB_CONCURRENCY", (multiprocessing.cpu_count() * 2) + 1))
worker_class = "sync"
timeout = int(os.environ.get("GUNICORN_TIMEOUT", "60"))
keepalive = int(os.environ.get("GUNICORN_KEEPALIVE", "5"))
max_requests = int(os.environ.get("GUNICORN_MAX_REQUESTS", "1000"))
max_requests_jitter = int(os.environ.get("GUNICORN_MAX_REQUESTS_JITTER", "50"))

accesslog = "-"
errorlog = "-"
loglevel = os.environ.get("GUNICORN_LOG_LEVEL", "info")

wsgi_app = "novaplatform_backend.wsgi:application"
