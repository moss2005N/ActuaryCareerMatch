import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def env_bool(name, default=False):
    """Read a boolean environment variable."""
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


def env_list(name, default=""):
    """Read a comma-separated environment variable."""
    return [item.strip() for item in os.getenv(name, default).split(",") if item.strip()]


SECRET_KEY = os.getenv("SECRET_KEY", "django-insecure-local-development-only")
DEBUG = env_bool("DEBUG", True)
ALLOWED_HOSTS = env_list("ALLOWED_HOSTS", "localhost,127.0.0.1")


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


if os.getenv("DB_ENGINE", "sqlite").lower() in {"postgres", "postgresql"}:
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
else:
    DATABASES = {
        "default": {
        'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / os.getenv("SQLITE_NAME", "db.sqlite3"),
        }
    }


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

EMAIL_BACKEND = os.getenv("EMAIL_BACKEND") or "django.core.mail.backends.console.EmailBackend"
DEFAULT_FROM_EMAIL = os.getenv("DEFAULT_FROM_EMAIL") or "Actuary Career Match <noreply@localhost>"
EMAIL_HOST = os.getenv("EMAIL_HOST") or "localhost"
EMAIL_PORT = int(os.getenv("EMAIL_PORT") or "25")
EMAIL_HOST_USER = os.getenv("EMAIL_HOST_USER") or ""
EMAIL_HOST_PASSWORD = os.getenv("EMAIL_HOST_PASSWORD") or ""
EMAIL_USE_TLS = env_bool("EMAIL_USE_TLS", False)
EMAIL_VERIFICATION_TIMEOUT_SECONDS = int(os.getenv("EMAIL_VERIFICATION_TIMEOUT_SECONDS") or "86400")

PHONE_VERIFICATION_BACKEND = os.getenv("PHONE_VERIFICATION_BACKEND") or "console"
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID") or ""
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN") or ""
TWILIO_VERIFY_SERVICE_SID = os.getenv("TWILIO_VERIFY_SERVICE_SID") or ""

OTP_EXPIRY_SECONDS = int(os.getenv("OTP_EXPIRY_SECONDS") or "600")
OTP_RESEND_COOLDOWN_SECONDS = int(os.getenv("OTP_RESEND_COOLDOWN_SECONDS") or "60")
OTP_MAX_SENDS_PER_PHONE_PER_HOUR = 5
OTP_MAX_ATTEMPTS_PER_CHALLENGE = 5
OTP_MAX_ATTEMPTS_PER_ACCOUNT_IP_PER_HOUR = 10
