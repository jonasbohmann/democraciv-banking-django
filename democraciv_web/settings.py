import os
import moneyed

from moneyed.localization import _FORMATTER
from decimal import ROUND_HALF_EVEN

GUARDIAN_RENDER_404 = True
GUARDIAN_RENDER_403 = True

BANK_NAME = "Bank of Democraciv"
BANK_ICON_URL = "https://cdn.discordapp.com/attachments/663076007426785300/717434510861533344/ezgif-5-8a4edb1f0306.png"

DEMOCRACIV_DISCORD_BOT_API_ADDRESS = "http://localhost:8000"
DEMOCRACIV_DISCORD_BOT_API_TWITCH_CALLBACK = DEMOCRACIV_DISCORD_BOT_API_ADDRESS + "/twitch/callback"

DEMOCRACIV_DISCORD_BOT_ADDRESS = "http://localhost:8080"
DEMOCRACIV_DISCORD_BOT_DM_ENDPOINT = DEMOCRACIV_DISCORD_BOT_ADDRESS + "/dm"

# Build paths inside the project like this: os.path.join(BASE_DIR, ...)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/3.0/howto/deployment/checklist/

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = 'INSERT_SECRET_KEY_HERE'

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = True

if not DEBUG:
    import sentry_sdk
    from sentry_sdk.integrations.django import DjangoIntegration

    sentry_sdk.init(
        dsn="INSERT_DSN_HERE",
        integrations=[DjangoIntegration()], send_default_pii=True)

ALLOWED_HOSTS = ['localhost']

# Application definition

INSTALLED_APPS = [
    'bank.apps.BankConfig',
    'django.contrib.contenttypes',
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'crispy_forms',
    'django_tables2',
    'rest_framework',
    'rest_framework.authtoken',
    'background_task',
    'guardian',
    'djmoney'
]

REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework.authentication.BasicAuthentication',
        'rest_framework.authentication.SessionAuthentication',
        'rest_framework.authentication.TokenAuthentication',

    ],
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 10
}

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'democraciv_web.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [os.path.join(BASE_DIR, 'templates')]
        ,
        'APP_DIRS': True,
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
    CSRF_COOKIE_SECURE = True
    SESSION_COOKIE_SECURE = True

WSGI_APPLICATION = 'democraciv_web.wsgi.application'

# Database
# https://docs.djangoproject.com/en/3.0/ref/settings/#databases

if not DEBUG:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.postgresql_psycopg2',
            'NAME': 'DB_NAME',
            'USER': 'DB_USER',
            'PASSWORD': 'DB_PASSWORD',
            'HOST': 'localhost',
            'PORT': '',
        }
    }

elif DEBUG:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': os.path.join(BASE_DIR, 'db.sqlite3'),
        }
    }

AUTH_USER_MODEL = 'bank.User'

# Password validation
# https://docs.djangoproject.com/en/3.0/ref/settings/#auth-password-validators

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

AUTHENTICATION_BACKENDS = (
    'django.contrib.auth.backends.ModelBackend',
    'guardian.backends.ObjectPermissionBackend',
)

ANONYMOUS_USER_NAME = None

# Internationalization
# https://docs.djangoproject.com/en/3.0/topics/i18n/

LANGUAGE_CODE = 'en-us'

TIME_ZONE = 'UTC'

USE_I18N = True

USE_L10N = True

USE_TZ = True

# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/3.0/howto/static-files/

STATIC_URL = '/static/'
STATIC_ROOT = os.path.join(BASE_DIR, 'bank/static/')

CRISPY_TEMPLATE_PACK = 'bootstrap4'

LOGIN_REDIRECT_URL = 'bank:account'
LOGIN_URL = 'login'

JAPAN = moneyed.add_currency(code="JPY", numeric="061", name="Japanese Yen", countries=('BOLIVIA',))

CIV = moneyed.add_currency(
    code='CIV',
    numeric='066',
    name='Civilization Coin',
    countries=('BOLIVIA',)
)

_FORMATTER.add_sign_definition('default', JAPAN, suffix=u'¥')

_FORMATTER.add_sign_definition(
    'default',
    CIV,
    suffix=u'C'
)

CURRENCIES = ("JPY", "CIV")
DJANGO_TABLES2_TEMPLATE = "django_tables2/bootstrap4.html"
