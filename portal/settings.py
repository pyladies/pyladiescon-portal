# import os 
# from pathlib import Path 
# import dj_database_url

# # BASE DIRECTORY

# BASE_DIR = Path(__file__).resolve().parent.parent

# # SECRET KEY

# SECRET_KEY = os.getenv("SECRET_KEY", "your-secret-key-here")

# # DEBUG MODE

# DEBUG = os.getenv("DEBUG", "True").lower() in ("true", "1")

# # ALLOWED HOSTS

# ALLOWED_HOSTS = os.getenv("DJANGO_ALLOWED_HOSTS", "127.0.0.1,localhost").split(",")

# # INSTALLED APPS

# INSTALLED_APPS = [ "django.contrib.admin", "django.contrib.auth", "django.contrib.contenttypes", "django.contrib.sessions", "django.contrib.messages", "django.contrib.staticfiles", "django.contrib.sites", "django_bootstrap5", "allauth", "allauth.account", "allauth.socialaccount", "portal", "volunteer", "portal_account", ]

# # MIDDLEWARE

# MIDDLEWARE = [ "django.middleware.security.SecurityMiddleware", "whitenoise.middleware.WhiteNoiseMiddleware", "django.contrib.sessions.middleware.SessionMiddleware", "django.middleware.common.CommonMiddleware", "django.middleware.csrf.CsrfViewMiddleware", "django.contrib.auth.middleware.AuthenticationMiddleware", "django.contrib.messages.middleware.MessageMiddleware", "django.middleware.clickjacking.XFrameOptionsMiddleware", "allauth.account.middleware.AccountMiddleware", ]

# # URL CONFIGURATION

# ROOT_URLCONF = "portal.urls"

# # TEMPLATES

# TEMPLATES = [ { "BACKEND": "django.template.backends.django.DjangoTemplates", "DIRS": [BASE_DIR / "templates"], "APP_DIRS": True, "OPTIONS": { "context_processors": [ "django.template.context_processors.debug", "django.template.context_processors.request", "django.contrib.auth.context_processors.auth", "django.contrib.messages.context_processors.messages", ], }, }, ]

# # WSGI APPLICATION

# WSGI_APPLICATION = "portal.wsgi.application"

# # DATABASE CONFIGURATION

# if os.getenv("DATABASE_URL"): DATABASES = {"default": dj_database_url.config(conn_max_age=600, conn_health_checks=True)} 
# else: DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": BASE_DIR / "db.sqlite3"}}

# # PASSWORD VALIDATORS

# AUTH_PASSWORD_VALIDATORS = [ {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"}, {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"}, {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"}, {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"}, ]

# # INTERNATIONALIZATION

# LANGUAGE_CODE = "en-us" 
# TIME_ZONE = "UTC" 
# USE_I18N = True 
# USE_TZ = True

# # STATIC FILES

# STATIC_URL = "static/" 
# STATIC_ROOT = BASE_DIR / "staticroot" 
# STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"

# # DEFAULT AUTO FIELD

# DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# # AUTHENTICATION BACKENDS

# AUTHENTICATION_BACKENDS = [ "django.contrib.auth.backends.ModelBackend", "allauth.account.auth_backends.AuthenticationBackend", ]

# # SITE ID

# SITE_ID = 1

# # DJANGO-ALLAUTH SETTINGS

# ACCOUNT_EMAIL_VERIFICATION = "mandatory" 
# ACCOUNT_SIGNUP_FIELDS = ["email", "username", "password1", "password2"] 
# ACCOUNT_LOGIN_METHODS = "email" 
# ACCOUNT_MAX_EMAIL_ADDRESSES = 3 
# ACCOUNT_FORMS = {"signup": "portal.forms.CustomSignupForm"}

# # EMAIL CONFIGURATION

# if os.getenv("DJANGO_EMAIL_HOST"): 
#     EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend" 
#     EMAIL_HOST = os.getenv("DJANGO_EMAIL_HOST") 
#     EMAIL_PORT = int(os.getenv("DJANGO_EMAIL_PORT", 587)) 
#     EMAIL_HOST_USER = os.getenv("DJANGO_EMAIL_HOST_USER") 
#     EMAIL_HOST_PASSWORD = os.getenv("DJANGO_EMAIL_HOST_PASSWORD") 
#     EMAIL_USE_TLS = os.getenv("DJANGO_EMAIL_USE_TLS", "True").lower() in ("true", "1") 
#     DEFAULT_FROM_EMAIL = os.getenv("DJANGO_DEFAULT_FROM_EMAIL") 
# else: EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"















import os
from pathlib import Path
from dotenv import load_dotenv
import dj_database_url

load_dotenv()


# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/5.1/howto/deployment/checklist/
# SECURITY WARNING: keep the secret key used in production secret!
# SECRET_KEY = os.environ.get("SECRET_KEY")
SECRET_KEY = os.environ.get("SECRET_KEY","h7Qap2XP9-cNEsRpXv7GN1KWIMYHnK4xcEdhRk3_2MXBfyV3b_yK53brLhs7TwFsvpo")

# SECURITY WARNING: don't run with debug turned on in production!
# DEBUG = bool(os.environ.get("DEBUG", default=0))
DEBUG =True



# ALLOWED_HOSTS should be in a list or tuple format
ALLOWED_HOSTS = os.environ.get("DJANGO_ALLOWED_HOSTS","127.0.0.1, localhost").split(",") # Default to localhosts if not set

# Application definition
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

BASE_DIR = Path(__file__).resolve().parent.parent

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
                "django.template.context_processors.request",
            ],
        },
    },
]

WSGI_APPLICATION = "portal.wsgi.application"

# Database
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

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]

# Internationalization
LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

# Static files (CSS, JavaScript, Images)
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticroot"
STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"

# Default primary key field type
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Authentication backends
AUTHENTICATION_BACKENDS = [
    "django.contrib.auth.backends.ModelBackend",  # Needed to login by username in Django admin, regardless of allauth
    "allauth.account.auth_backends.AuthenticationBackend",  # allauth specific authentication methods, such as login by email
]

SITE_ID = 1

# Email settings for verification
ACCOUNT_EMAIL_VERIFICATION = "mandatory"
ACCOUNT_EMAIL_VERIFICATION_BY_CODE_ENABLED = True
ACCOUNT_EMAIL_SUBJECT_PREFIX = "[PyLadiesCon Dev] "
LOGIN_REDIRECT_URL = "/"

# Fixed the ACCOUNT_LOGIN_METHODS and added email to it
ACCOUNT_LOGIN_METHODS = ["username", "email"]

# Updated the ACCOUNT_SIGNUP_FIELDS to include 'email'
ACCOUNT_SIGNUP_FIELDS = ["email*", "username*", "first_name*", "last_name*", "password1*", "password2*"]

ACCOUNT_MAX_EMAIL_ADDRESSES = 3

# Use custom signup form
ACCOUNT_FORMS = {
    'signup': 'portal.forms.CustomSignupForm'
}

# Email settings - fallback to console if env variables are not set
if "DJANGO_EMAIL_HOST" in os.environ:
    EMAIL_HOST = os.getenv("DJANGO_EMAIL_HOST")
    EMAIL_PORT = os.getenv("DJANGO_EMAIL_PORT")
    EMAIL_HOST_USER = os.getenv("DJANGO_EMAIL_HOST_USER")
    EMAIL_HOST_PASSWORD = os.getenv("DJANOG_EMAIL_HOST_PASSWORD")
    EMAIL_USE_TLS = os.getenv("DJANGO_EMAIL_USE_TLS")
    DEFAULT_FROM_EMAIL = os.getenv("DJANGO_DEFAULT_FROM_EMAIL")
else:
    EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

# Bootstrap 5 settings for styling forms
BOOTSTRAP5 = {
    "css_url": {
        "url": "https://cdn.jsdelivr.net/npm/bootstrap@5.2.0/dist/css/bootstrap.min.css",
        "integrity": "sha384-gH2yIJqKdNHPEq0n4Mqa/HGKIhSkIHeL5AyhkYV8i59U5AR6csBvApHHNl/vI1Bx",
        "crossorigin": "anonymous",
    },
    "javascript_url": {
        "url": "https://cdn.jsdelivr.net/npm/bootstrap@5.2.0/dist/js/bootstrap.bundle.min.js",
        "integrity": "sha384-A3rJD856KowSb7dwlZdYEkO39Gagi7vIsF0jrRAoQmDKKtQBHUuLZ9AsSv4jD4Xa",
        "crossorigin": "anonymous",
    },
    "theme_url": None,
    "color_mode": None,
    "javascript_in_head": False,
    "wrapper_class": "mb-3",
    "inline_wrapper_class": "",
    "horizontal_label_class": "col-sm-2",
    "horizontal_field_class": "col-sm-10",
    "horizontal_field_offset_class": "offset-sm-2",
    "hyphenate_attribute_prefixes": ["data"],
    "set_placeholder": True,
    "required_css_class": "",
    "error_css_class": "",
    "success_css_class": "",
    "server_side_validation": True,
    "formset_renderers": {
        "default": "django_bootstrap5.renderers.FormsetRenderer",
    },
    "form_renderers": {
        "default": "django_bootstrap5.renderers.FormRenderer",
    },
    "field_renderers": {
        "default": "django_bootstrap5.renderers.FieldRenderer",
    },
}