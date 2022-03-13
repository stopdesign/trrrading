from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

DEBUG = False


# TODO: remove
SECRET_KEY = "dummy"
STATIC_ROOT = BASE_DIR.parents[1] / "www/static"
MEDIA_ROOT = BASE_DIR.parents[1] / "www/media"
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}


INTERNAL_IPS = [
    "0.0.0.0",
    "127.0.0.1",
]

ALLOWED_HOSTS = [
    "0.0.0.0",
    "127.0.0.1",
    "localhost",
]

ADMINS = [
    "gregory@stopdesign.ru",
]


# Application definition
INSTALLED_APPS = [
    # django
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "corsheaders",
    # project
    "main",
    "project",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    # "main.middleware.login_required.LoginRequiredMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "project.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": ["project/templates",],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "django_settings_export.settings_export",
            ],
        },
    },
]

DEFAULT_AUTO_FIELD = 'django.db.models.AutoField'


# DEFAULT_FILE_STORAGE = 'project.helpers.services.ASCIIFileSystemStorage'

STATICFILES_STORAGE = 'django.contrib.staticfiles.storage.ManifestStaticFilesStorage'

# Collect static files from the frontend build directory (if available)
STATICFILES_DIRS = []
front_dist_path = BASE_DIR.parents[1] / "front/build/static"
if front_dist_path.exists():
    STATICFILES_DIRS.append(front_dist_path)


WSGI_APPLICATION = "project.wsgi.application"


# AUTH_USER_MODEL = "main.User"
PASSWORD_RESET_TIMEOUT_DAYS = 1


# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
USE_I18N = False
USE_L10N = False
USE_TZ = True
TIME_ZONE = "UTC"

DATE_FORMAT = 'd E Y'
SHORT_DATE_FORMAT = 'd.m.Y'
DATETIME_FORMAT = 'd.m.Y, H:i:s'
SHORT_DATETIME_FORMAT = 'd.m.Y, H:i:s'

STATIC_URL = "/static/"
MEDIA_URL = "/md/"

APPEND_SLASH = False

CORS_ALLOW_ALL_ORIGINS = True

# Add reversion models to admin interface:
ADD_REVERSION_ADMIN = True

# optional settings:
REVERSION_COMPARE_FOREIGN_OBJECTS_AS_ID = False
REVERSION_COMPARE_IGNORE_NOT_REGISTERED = False


SETTINGS_EXPORT = [
    "MEDIA_ROOT",
    "STATIC_ROOT",
]


TREDIS_HOST = "127.0.0.1"
TREDIS_PORT = 6379
TREDIS_PASSWORD = None
TREDIS_DB = 0


# Alerts
TELEGRAM_TOKEN = None
TELEGRAM_CHANNEL_ID = "*****"
TELEGRAM_USERNAME = ""
