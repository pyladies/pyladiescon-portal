import os
from pathlib import Path
import dj_database_url

BASE_DIR = Path(__file__).resolve().parent.parent

#  Loaded SECRET_KEY from environment variables (Best Practice)
SECRET_KEY = os.environ.get("SECRET_KEY", "9n7jRfCGjLSkl8rhgNo40jNysD_8e7zf6VPtg87UK-TGAKdLFkiPcw6kXzbfaZP2njM")

DEBUG = True
ALLOWED_HOSTS = os.environ.get("DJANGO_ALLOWED_HOSTS", "127.0.0.1,localhost").split(",")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.sites",
    "django_bootstrap5",
    "allauth",
    "allauth.account",
    "allauth.socialaccount",  #  Added this (was missing before)
    "portal",
    "volunteer",
    "portal_account",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "allauth.account.middleware.AccountMiddleware",
]

ROOT_URLCONF = "portal.urls"
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "portal.wsgi.application"

if os.environ.get("DATABASE_URL", None) is not None:
    DATABASES = {
        "default": dj_database_url.config(
            conn_max_age=600,
            conn_health_checks=True,
        )
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": os.environ.get("SQL_ENGINE", "django.db.backends.sqlite3"),
            "NAME": os.environ.get("SQL_DATABASE", BASE_DIR / "db.sqlite3"),
            "USER": os.environ.get("SQL_USER", "user"),
            "PASSWORD": os.environ.get("SQL_PASSWORD", "password"),
            "HOST": os.environ.get("SQL_HOST", "localhost"),
            "PORT": os.environ.get("SQL_PORT", "5432"),
        }
    }

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticroot"
STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

AUTHENTICATION_BACKENDS = [
    "django.contrib.auth.backends.ModelBackend",
    "allauth.account.auth_backends.AuthenticationBackend",
]

SITE_ID = 1

ACCOUNT_EMAIL_VERIFICATION = "mandatory"
ACCOUNT_EMAIL_VERIFICATION_BY_CODE_ENABLED = True
ACCOUNT_EMAIL_SUBJECT_PREFIX = "[PyLadiesCon Dev] "
LOGIN_REDIRECT_URL = "/"

#  Previously commented out, now modified and fixed
# ACCOUNT_LOGIN_METHOD = "username"
# ACCOUNT_SIGNUP_FIELDS = ["email", "username", "first_name", "last_name", "password1", "password2"]

#  Removed "*" from `ACCOUNT_SIGNUP_FIELDS`, as it's not valid in Django
ACCOUNT_SIGNUP_FIELDS = ["email", "username", "first_name", "last_name", "password1", "password2"]  

#  Fixed incorrect key name (`ACCOUNT_LOGIN_METHODS` → `ACCOUNT_LOGIN_METHOD`)
ACCOUNT_LOGIN_METHOD = "username"  

ACCOUNT_MAX_EMAIL_ADDRESSES = 3

ACCOUNT_FORMS = {
    'signup': 'portal.forms.CustomSignupForm'
}

if "DJANGO_EMAIL_HOST" in os.environ:
    EMAIL_HOST = os.getenv("DJANGO_EMAIL_HOST")
    EMAIL_PORT = os.getenv("DJANGO_EMAIL_PORT")
    EMAIL_HOST_USER = os.getenv("DJANGO_EMAIL_HOST_USER")
    EMAIL_HOST_PASSWORD = os.getenv("DJANGO_EMAIL_HOST_PASSWORD")  #  Fixed typo
    EMAIL_USE_TLS = os.getenv("DJANGO_EMAIL_USE_TLS")
    DEFAULT_FROM_EMAIL = os.getenv("DJANGO_DEFAULT_FROM_EMAIL")
else:
    EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"






