from pathlib import Path

import environ
from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent

env = environ.Env(
    DJANGO_DEBUG=(bool, False),
    DJANGO_ALLOWED_HOSTS=(list, []),
    TENANT_RATE_LIMIT=(str, "120/min"),
    ALLOWED_MODELS=(list, ["gpt-4o-mini", "gpt-4o"]),
)

ENV_FILE = BASE_DIR / ".env"
if ENV_FILE.exists():
    environ.Env.read_env(ENV_FILE)

PLACEHOLDER_SECRET_KEY = "change-me"

SECRET_KEY = env("DJANGO_SECRET_KEY")
DEBUG = env("DJANGO_DEBUG")
ALLOWED_HOSTS = env("DJANGO_ALLOWED_HOSTS")
TENANT_RATE_LIMIT = env("TENANT_RATE_LIMIT")
ALLOWED_MODELS = env("ALLOWED_MODELS")

if not DEBUG and SECRET_KEY == PLACEHOLDER_SECRET_KEY:
    raise ImproperlyConfigured("DJANGO_SECRET_KEY must be set to a real value when DEBUG is off.")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "drf_spectacular",
    "tenants",
    "agents",
    "knowledge",
    "tools",
    "evaluation",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

DATABASES = {"default": env.db("DATABASE_URL")}

DATABASE_CONNECT_TIMEOUT_SECONDS = 5

if DATABASES["default"]["ENGINE"] != "django.db.backends.postgresql":
    raise ImproperlyConfigured("DATABASE_URL must point to PostgreSQL with the pgvector extension.")

DATABASES["default"].setdefault("OPTIONS", {})["connect_timeout"] = DATABASE_CONNECT_TIMEOUT_SECONDS

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
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

REST_FRAMEWORK = {
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "DEFAULT_PARSER_CLASSES": ["rest_framework.parsers.JSONParser"],
    "DEFAULT_AUTHENTICATION_CLASSES": ["tenants.authentication.ApiKeyAuthentication"],
    "DEFAULT_PERMISSION_CLASSES": ["tenants.authentication.IsTenantAuthenticated"],
    "DEFAULT_THROTTLE_CLASSES": ["tenants.throttling.TenantRateThrottle"],
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
}

SPECTACULAR_SETTINGS = {
    "TITLE": "Agent Platform API",
    "DESCRIPTION": "Multi-tenant API to define and run LLM agents.",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "SCHEMA_PATH_PREFIX": "/v1",
    "COMPONENT_SPLIT_REQUEST": True,
}

CELERY_BROKER_URL = env("REDIS_URL", default="redis://127.0.0.1:56379/0")
CELERY_RESULT_BACKEND = CELERY_BROKER_URL
CELERY_TASK_ALWAYS_EAGER = env.bool("CELERY_TASK_ALWAYS_EAGER", default=False)
CELERY_TASK_EAGER_PROPAGATES = True
CELERY_TASK_SERIALIZER = "json"
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True

LLM_PROVIDER = env("LLM_PROVIDER", default="azure")
AZURE_OPENAI_ENDPOINT = env("AZURE_OPENAI_ENDPOINT", default="")
AZURE_OPENAI_API_KEY = env("AZURE_OPENAI_API_KEY", default="")
AZURE_OPENAI_API_VERSION = env("AZURE_OPENAI_API_VERSION", default="2024-10-21")
RUN_TIMEOUT_SECONDS = env.float("RUN_TIMEOUT_SECONDS", default=60.0)
RUN_MAX_RETRIES = env.int("RUN_MAX_RETRIES", default=3)
RUN_RETRY_BACKOFF_SECONDS = env.float("RUN_RETRY_BACKOFF_SECONDS", default=2.0)

EMBEDDER = env("EMBEDDER", default="hashing")
MAX_DOCUMENT_BYTES = env.int("MAX_DOCUMENT_BYTES", default=1024 * 1024)
CHUNK_SIZE = env.int("CHUNK_SIZE", default=800)
CHUNK_OVERLAP = env.int("CHUNK_OVERLAP", default=100)
RETRIEVAL_TOP_K = env.int("RETRIEVAL_TOP_K", default=4)
RETRIEVAL_MIN_SCORE = env.float("RETRIEVAL_MIN_SCORE", default=0.1)
TOOL_ALLOWED_DOMAINS = env.list("TOOL_ALLOWED_DOMAINS", default=[])
TOOL_TIMEOUT_SECONDS = env.float("TOOL_TIMEOUT_SECONDS", default=10.0)
TOOL_MAX_RESPONSE_BYTES = env.int("TOOL_MAX_RESPONSE_BYTES", default=64 * 1024)
MAX_TOOL_STEPS = env.int("MAX_TOOL_STEPS", default=5)
LANGFUSE_HOST = env("LANGFUSE_HOST", default="")
LANGFUSE_PUBLIC_KEY = env("LANGFUSE_PUBLIC_KEY", default="")
LANGFUSE_SECRET_KEY = env("LANGFUSE_SECRET_KEY", default="")
DEFAULT_MODEL_PRICING = {
    "gpt-4o-mini": {"input": 0.15, "output": 0.60},
    "gpt-4o": {"input": 2.50, "output": 10.00},
}
MODEL_PRICING = env.json("MODEL_PRICING", default=DEFAULT_MODEL_PRICING)

LOG_LEVEL = env("LOG_LEVEL", default="INFO")

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {"json": {"()": "config.logs.JsonFormatter"}},
    "handlers": {"console": {"class": "logging.StreamHandler", "formatter": "json"}},
    "root": {"handlers": ["console"], "level": LOG_LEVEL},
    "loggers": {"celery": {"level": "WARNING"}, "django.server": {"level": "WARNING"}},
}
