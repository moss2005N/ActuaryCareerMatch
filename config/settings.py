import os
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent


def env_bool(name, default=False):
    """Read a strict boolean environment variable."""
    value = os.getenv(name)
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ImproperlyConfigured(f"{name} must be a boolean value.")


def env_list(name, default=""):
    """Read a comma-separated environment variable."""
    return [item.strip() for item in os.getenv(name, default).split(",") if item.strip()]


DJANGO_ENVIRONMENT = os.getenv("DJANGO_ENVIRONMENT", "production").strip().lower()
if DJANGO_ENVIRONMENT not in {"development", "test", "production"}:
    raise ImproperlyConfigured(
        "DJANGO_ENVIRONMENT must be development, test, or production."
    )

IS_PRODUCTION = DJANGO_ENVIRONMENT == "production"
DEBUG = env_bool("DEBUG", False)
if IS_PRODUCTION and DEBUG:
    raise ImproperlyConfigured("DEBUG cannot be enabled in production.")

SECRET_KEY = os.getenv("SECRET_KEY", "")
if not IS_PRODUCTION and not SECRET_KEY:
    SECRET_KEY = "django-insecure-explicit-local-development-only"
if IS_PRODUCTION and (
    len(SECRET_KEY) < 50
    or len(set(SECRET_KEY)) < 5
    or SECRET_KEY.startswith("django-insecure-")
):
    raise ImproperlyConfigured(
        "Production requires a strong SECRET_KEY of at least 50 characters."
    )

ALLOWED_HOSTS = env_list(
    "ALLOWED_HOSTS",
    "" if IS_PRODUCTION else "localhost,127.0.0.1,[::1],testserver",
)
if IS_PRODUCTION and (not ALLOWED_HOSTS or "*" in ALLOWED_HOSTS):
    raise ImproperlyConfigured(
        "Production requires explicit ALLOWED_HOSTS and does not allow '*'."
    )

CSRF_TRUSTED_ORIGINS = env_list("CSRF_TRUSTED_ORIGINS")
if IS_PRODUCTION and any(
    not origin.startswith("https://") for origin in CSRF_TRUSTED_ORIGINS
):
    raise ImproperlyConfigured(
        "Production CSRF_TRUSTED_ORIGINS entries must use https://."
    )

SECURE_SSL_REDIRECT = env_bool("SECURE_SSL_REDIRECT", IS_PRODUCTION)
SESSION_COOKIE_SECURE = env_bool("SESSION_COOKIE_SECURE", IS_PRODUCTION)
CSRF_COOKIE_SECURE = env_bool("CSRF_COOKIE_SECURE", IS_PRODUCTION)
SECURE_HSTS_SECONDS = int(os.getenv("SECURE_HSTS_SECONDS", "0"))
SECURE_HSTS_INCLUDE_SUBDOMAINS = env_bool("SECURE_HSTS_INCLUDE_SUBDOMAINS", False)
SECURE_HSTS_PRELOAD = env_bool("SECURE_HSTS_PRELOAD", False)
SECURE_REFERRER_POLICY = "same-origin"

# Enable only when a trusted reverse proxy strips inbound X-Forwarded-Proto and
# sets it itself. The header name and secure value are deliberately not
# configurable, preventing trust in an arbitrary client-controlled header.
if env_bool("TRUST_X_FORWARDED_PROTO", False):
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")


INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'core',
    'accounts.apps.AccountsConfig',
    'profiles',
    'jobs.apps.JobsConfig',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'


DB_ENGINE = os.getenv("DB_ENGINE", "" if IS_PRODUCTION else "sqlite").lower()
if IS_PRODUCTION and not DB_ENGINE:
    raise ImproperlyConfigured("Production requires an explicit DB_ENGINE.")
if DB_ENGINE in {"postgres", "postgresql"}:
    if IS_PRODUCTION:
        missing_database_values = [
            name for name in ("DB_NAME", "DB_USER", "DB_PASSWORD", "DB_HOST")
            if not os.getenv(name)
        ]
        if missing_database_values:
            raise ImproperlyConfigured(
                "Production PostgreSQL configuration is incomplete: "
                + ", ".join(missing_database_values)
            )
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": os.getenv("DB_NAME", "actuary_career_match"),
            "USER": os.getenv("DB_USER", "postgres"),
            "PASSWORD": os.getenv("DB_PASSWORD", ""),
            "HOST": os.getenv("DB_HOST", "localhost"),
            "PORT": os.getenv("DB_PORT", "5432"),
        }
    }
elif DB_ENGINE == "sqlite":
    DATABASES = {
        "default": {
        'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / os.getenv("SQLITE_NAME", "db.sqlite3"),
        }
    }
else:
    raise ImproperlyConfigured("DB_ENGINE must be sqlite, postgres, or postgresql.")


# Password validation
# https://docs.djangoproject.com/en/6.0/ref/settings/#auth-password-validators

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


# Internationalization
# https://docs.djangoproject.com/en/6.0/topics/i18n/

LANGUAGE_CODE = 'en-us'

TIME_ZONE = 'UTC'

USE_I18N = True

USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/6.0/howto/static-files/

STATIC_URL = 'static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'

MEDIA_URL = 'media/'
MEDIA_ROOT = BASE_DIR / 'media'
PRIVATE_MEDIA_ROOT = BASE_DIR / 'private_media'

AUTH_USER_MODEL = 'accounts.User'

LOGIN_REDIRECT_URL = 'profiles:detail'
LOGOUT_REDIRECT_URL = 'core:home'
LOGIN_URL = 'accounts:login'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

AUTHENTICATION_BACKENDS = ["accounts.backends.UsernameOrEmailBackend"]

EMAIL_BACKEND = os.getenv("EMAIL_BACKEND") or (
    "" if IS_PRODUCTION else "django.core.mail.backends.console.EmailBackend"
)
DEFAULT_FROM_EMAIL = os.getenv("DEFAULT_FROM_EMAIL") or (
    "" if IS_PRODUCTION else "Actuary Career Match <noreply@localhost>"
)
EMAIL_HOST = os.getenv("EMAIL_HOST") or "localhost"
EMAIL_PORT = int(os.getenv("EMAIL_PORT") or "25")
EMAIL_HOST_USER = os.getenv("EMAIL_HOST_USER") or ""
EMAIL_HOST_PASSWORD = os.getenv("EMAIL_HOST_PASSWORD") or ""
EMAIL_USE_TLS = env_bool("EMAIL_USE_TLS", False)
EMAIL_VERIFICATION_TIMEOUT_SECONDS = int(os.getenv("EMAIL_VERIFICATION_TIMEOUT_SECONDS") or "86400")

PHONE_VERIFICATION_BACKEND = os.getenv("PHONE_VERIFICATION_BACKEND") or (
    "" if IS_PRODUCTION else "console"
)
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID") or ""
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN") or ""
TWILIO_VERIFY_SERVICE_SID = os.getenv("TWILIO_VERIFY_SERVICE_SID") or ""

if IS_PRODUCTION:
    unsafe_email_backends = {
        "",
        "django.core.mail.backends.console.EmailBackend",
        "django.core.mail.backends.locmem.EmailBackend",
        "django.core.mail.backends.dummy.EmailBackend",
    }
    if EMAIL_BACKEND in unsafe_email_backends or not DEFAULT_FROM_EMAIL:
        raise ImproperlyConfigured(
            "Production requires a delivery-capable EMAIL_BACKEND and DEFAULT_FROM_EMAIL."
        )
    if (
        EMAIL_BACKEND == "django.core.mail.backends.smtp.EmailBackend"
        and not os.getenv("EMAIL_HOST")
    ):
        raise ImproperlyConfigured(
            "Production SMTP email requires an explicit EMAIL_HOST."
        )
    if PHONE_VERIFICATION_BACKEND != "twilio" or not all(
        (TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_VERIFY_SERVICE_SID)
    ):
        raise ImproperlyConfigured(
            "Production requires the Twilio verification backend and all Twilio credentials."
        )

OTP_EXPIRY_SECONDS = int(os.getenv("OTP_EXPIRY_SECONDS") or "600")
OTP_RESEND_COOLDOWN_SECONDS = int(os.getenv("OTP_RESEND_COOLDOWN_SECONDS") or "60")
OTP_MAX_SENDS_PER_PHONE_PER_HOUR = 5
OTP_MAX_ATTEMPTS_PER_CHALLENGE = 5
OTP_MAX_ATTEMPTS_PER_ACCOUNT_IP_PER_HOUR = 10

AI_RESUME_PROVIDER = os.getenv("AI_RESUME_PROVIDER", "mock")
AI_MODEL = os.getenv("AI_MODEL", "")
AI_API_KEY = os.getenv("AI_API_KEY", "")
RESUME_ANALYSIS_MAX_PAGES = int(os.getenv("RESUME_ANALYSIS_MAX_PAGES") or "10")
RESUME_ANALYSIS_MAX_CHARACTERS = int(os.getenv("RESUME_ANALYSIS_MAX_CHARACTERS") or "50000")

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "loggers": {
        "jobs.imports": {
            "handlers": ["console"],
            "level": os.getenv("JOB_IMPORT_LOG_LEVEL", "INFO"),
            "propagate": False,
        }
    },
}
