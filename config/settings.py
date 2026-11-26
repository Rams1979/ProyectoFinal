import os
from pathlib import Path

import dj_database_url

BASE_DIR = Path(__file__).resolve().parent.parent

# Prototipo: sin datos reales. En Railway se define SECRET_KEY como variable.
SECRET_KEY = os.environ.get("SECRET_KEY", "clave-solo-para-desarrollo-local")
DEBUG = os.environ.get("DEBUG", "0") == "1"
ALLOWED_HOSTS = ["*"]

_dominio = os.environ.get("RAILWAY_PUBLIC_DOMAIN")
CSRF_TRUSTED_ORIGINS = [f"https://{_dominio}"] if _dominio else []

INSTALLED_APPS = [
    "django.contrib.staticfiles",
    "hotel",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {"context_processors": ["django.template.context_processors.request"]},
    }
]

WSGI_APPLICATION = "config.wsgi.application"

# PostgreSQL en Railway (DATABASE_URL); SQLite solo para correr en local.
DATABASES = {
    "default": dj_database_url.config(
        default=f"sqlite:///{BASE_DIR / 'db.sqlite3'}",
        conn_max_age=600,
    )
}

LANGUAGE_CODE = "es"
TIME_ZONE = "America/Costa_Rica"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
