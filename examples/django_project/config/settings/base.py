import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "demo-only-not-secret")
ALLOWED_HOSTS = ["localhost", "127.0.0.1"]

DJANGO_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.forms",
]
LOCAL_APPS = [
    "catalog.apps.CatalogConfig",
    "accounts",
]
INSTALLED_APPS = DJANGO_APPS + LOCAL_APPS

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.template.context_processors.i18n",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ]
        },
    },
    {
        "BACKEND": "django.template.backends.jinja2.Jinja2",
        "DIRS": [],
        "APP_DIRS": True,
    },
]
# Widget templates (widgets/star_rating.html) live in the project's templates/.
FORM_RENDERER = "django.forms.renderers.TemplatesSetting"

# The demo has no database: sessions live in signed cookies.
DATABASES: dict = {}
SESSION_ENGINE = "django.contrib.sessions.backends.signed_cookies"
LOGIN_URL = "accounts:login"

LANGUAGE_CODE = "en"
USE_I18N = True

STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
