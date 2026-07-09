import os
import sys
from pathlib import Path
from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent


def env_bool(name, default=False):
    value = os.environ.get(name)
    if value is None:
        return default
    return value.lower() in {"1", "true", "yes", "on"}


def env_list(name, default=""):
    value = os.environ.get(name, default)
    return [item.strip() for item in value.split(",") if item.strip()]


SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "")
DEBUG = env_bool("DJANGO_DEBUG", default=False)
default_allowed_hosts = "localhost,127.0.0.1,[::1]" if DEBUG else ""
ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", default_allowed_hosts)
CSRF_TRUSTED_ORIGINS = env_list("DJANGO_CSRF_TRUSTED_ORIGINS", "")

if not SECRET_KEY:
    if DEBUG:
        SECRET_KEY = "dev-only-insecure-key-change-before-prod"
    else:
        raise RuntimeError("DJANGO_SECRET_KEY must be set when DJANGO_DEBUG=False")

if not DEBUG and not ALLOWED_HOSTS:
    raise RuntimeError("DJANGO_ALLOWED_HOSTS must be set when DJANGO_DEBUG=False")

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'accounts.apps.AccountsConfig',
    'dashboard',
    'students',
    'teachers',
    'courses',
    'subscriptions',
    'payments',
    'notifications',
    'exams',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'novaplatform_backend.request_context.RequestContextMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'novaplatform_backend.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': DEBUG,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

if not DEBUG:
    TEMPLATES[0]['OPTIONS']['loaders'] = [
        (
            'django.template.loaders.cached.Loader',
            [
                'django.template.loaders.filesystem.Loader',
                'django.template.loaders.app_directories.Loader',
            ],
        )
    ]

WSGI_APPLICATION = 'novaplatform_backend.wsgi.application'
ASGI_APPLICATION = 'novaplatform_backend.asgi.application'

if DEBUG:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }
else:
    db_engine = os.environ.get("DB_ENGINE", "").strip().lower()
    if db_engine not in {"postgres", "postgresql", "sqlite"}:
        raise ImproperlyConfigured(
            "Production database is not configured correctly. "
            "Set DB_ENGINE to one of: postgres, postgresql, sqlite. "
            "If using PostgreSQL, also provide DB_NAME, DB_USER, DB_PASSWORD, DB_HOST, DB_PORT."
        )

    if db_engine in {"postgres", "postgresql"}:
        required_db_env_vars = ["DB_NAME", "DB_USER", "DB_PASSWORD", "DB_HOST", "DB_PORT"]
        missing_db_env_vars = [name for name in required_db_env_vars if not os.environ.get(name, "").strip()]
        if missing_db_env_vars:
            raise ImproperlyConfigured(
                "Missing required PostgreSQL environment variables: "
                f"{', '.join(missing_db_env_vars)}. "
                "Required variables when DJANGO_DEBUG=False and DB_ENGINE is PostgreSQL: "
                "DB_ENGINE, DB_NAME, DB_USER, DB_PASSWORD, DB_HOST, DB_PORT."
            )

        DATABASES = {
            "default": {
                "ENGINE": "django.db.backends.postgresql",
                "NAME": os.environ["DB_NAME"],
                "USER": os.environ["DB_USER"],
                "PASSWORD": os.environ["DB_PASSWORD"],
                "HOST": os.environ["DB_HOST"],
                "PORT": os.environ["DB_PORT"],
                "CONN_MAX_AGE": int(os.environ.get("DB_CONN_MAX_AGE", "60")),
                "OPTIONS": {
                    "sslmode": os.environ.get("DB_SSLMODE", "require"),
                },
            }
        }
    else:
        DATABASES = {
            "default": {
                "ENGINE": "django.db.backends.sqlite3",
                "NAME": BASE_DIR / "db.sqlite3",
            }
        }

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

LANGUAGE_CODE = 'ar'
TIME_ZONE = 'Asia/Damascus'
USE_I18N = True
USE_TZ = True

STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_DIRS = [BASE_DIR / 'static']
STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}

MEDIA_URL = '/media/'
MEDIA_ROOT = Path(os.environ.get("DJANGO_MEDIA_ROOT", BASE_DIR / 'media'))

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = 'DENY'
SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY = env_bool("DJANGO_CSRF_COOKIE_HTTPONLY", default=False)
SECURE_REFERRER_POLICY = os.environ.get("DJANGO_SECURE_REFERRER_POLICY", "same-origin")
SECURE_CROSS_ORIGIN_OPENER_POLICY = os.environ.get("DJANGO_SECURE_CROSS_ORIGIN_OPENER_POLICY", "same-origin")
ENABLE_PROXY_HEADERS = env_bool("ENABLE_PROXY_HEADERS", default=False)
if ENABLE_PROXY_HEADERS:
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    USE_X_FORWARDED_HOST = env_bool("DJANGO_USE_X_FORWARDED_HOST", default=True)
else:
    SECURE_PROXY_SSL_HEADER = None
    USE_X_FORWARDED_HOST = False
CSRF_COOKIE_SAMESITE = os.environ.get("DJANGO_CSRF_COOKIE_SAMESITE", "Lax")
SESSION_COOKIE_SAMESITE = os.environ.get("DJANGO_SESSION_COOKIE_SAMESITE", "Lax")

SECURE_SSL_REDIRECT = env_bool("DJANGO_SECURE_SSL_REDIRECT", default=not DEBUG)
SECURE_HSTS_SECONDS = int(os.environ.get("DJANGO_SECURE_HSTS_SECONDS", "0" if DEBUG else "31536000"))
SECURE_HSTS_INCLUDE_SUBDOMAINS = env_bool("DJANGO_SECURE_HSTS_INCLUDE_SUBDOMAINS", default=not DEBUG)
SECURE_HSTS_PRELOAD = env_bool("DJANGO_SECURE_HSTS_PRELOAD", default=not DEBUG)
CSRF_COOKIE_SECURE = env_bool("DJANGO_CSRF_COOKIE_SECURE", default=not DEBUG)
SESSION_COOKIE_SECURE = env_bool("DJANGO_SESSION_COOKIE_SECURE", default=not DEBUG)


LOG_DIR = Path(os.environ.get("DJANGO_LOG_DIR", BASE_DIR / "logs"))
LOG_DIR.mkdir(parents=True, exist_ok=True)

LOG_LEVEL = os.environ.get("DJANGO_LOG_LEVEL", "INFO")

LOGIN_IP_FAILED_LIMIT = int(os.environ.get("LOGIN_IP_FAILED_LIMIT", "20"))
LOGIN_IP_FAILED_WINDOW_SECONDS = int(os.environ.get("LOGIN_IP_FAILED_WINDOW_SECONDS", "900"))
LOGIN_IP_BLOCK_SECONDS = int(os.environ.get("LOGIN_IP_BLOCK_SECONDS", "900"))
LOGIN_SUSPICIOUS_WINDOW_SECONDS = int(os.environ.get("LOGIN_SUSPICIOUS_WINDOW_SECONDS", "900"))
LOGIN_SUSPICIOUS_IP_USERNAMES_THRESHOLD = int(os.environ.get("LOGIN_SUSPICIOUS_IP_USERNAMES_THRESHOLD", "5"))
LOGIN_SUSPICIOUS_USERNAME_IPS_THRESHOLD = int(os.environ.get("LOGIN_SUSPICIOUS_USERNAME_IPS_THRESHOLD", "5"))

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "%(asctime)s [%(levelname)s] %(name)s:%(lineno)d %(message)s",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "verbose",
        },
        "file": {
            "class": "logging.handlers.TimedRotatingFileHandler",
            "filename": str(LOG_DIR / "django.log"),
            "when": "midnight",
            "backupCount": 14,
            "formatter": "verbose",
        },
    },
    "root": {
        "handlers": ["console", "file"],
        "level": LOG_LEVEL,
    },
    "loggers": {
        "django.security": {
            "handlers": ["console", "file"],
            "level": "WARNING",
            "propagate": False,
        },
        "django.request": {
            "handlers": ["console", "file"],
            "level": "WARNING",
            "propagate": False,
        },
    },
}

# Keep expected 4xx request warnings from polluting test output.
if "test" in sys.argv:
    LOGGING["loggers"]["django.request"]["level"] = "ERROR"
