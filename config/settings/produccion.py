"""
Configuración de producción para Luca en Vercel + Supabase.

# SEGURIDAD / REQ-16: Exige HTTPS, cookies seguras, HSTS y almacenamiento S3 en Supabase.
# ADR-004: Conecta al Transaction Pooler de Supabase (puerto 6543) con CONN_MAX_AGE=0
# y DISABLE_SERVER_SIDE_CURSORS=True para compatibilidad serverless.
"""
import os

import dj_database_url

from .base import *  # noqa: F401, F403

DEBUG = False

DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()
if DATABASE_URL:
    db_config = dj_database_url.parse(
        DATABASE_URL,
        conn_max_age=0,
        ssl_require=True,
    )
    db_config["DISABLE_SERVER_SIDE_CURSORS"] = True
    if "postgresql" in db_config.get("ENGINE", ""):
        db_config.setdefault("OPTIONS", {})["options"] = "-c search_path=public,extensions"
    DATABASES = {"default": db_config}
else:
    # Permite ejecutar `manage.py check --deploy` en CI sin credenciales reales
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }

# WhiteNoise con compresión y manifest para caché eficiente en Vercel
STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}

# Almacenamiento S3-compatible de Supabase cuando están presentes las variables
if os.environ.get("SUPABASE_S3_ENDPOINT") and os.environ.get("SUPABASE_S3_KEY"):
    STORAGES["default"] = {
        "BACKEND": "storages.backends.s3.S3Storage",
        "OPTIONS": {
            "endpoint_url": os.environ["SUPABASE_S3_ENDPOINT"],
            "access_key": os.environ["SUPABASE_S3_KEY"],
            "secret_key": os.environ["SUPABASE_S3_SECRET"],
            "bucket_name": os.environ.get("SUPABASE_BUCKET", "luca-archivos"),
            "default_acl": None,
            "querystring_auth": True,
        },
    }

# SEGURIDAD: Cookies y transporte HTTPS estrictos en producción
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
