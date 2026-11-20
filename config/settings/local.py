"""
Configuración de desarrollo local para Luca.

Usa SQLite automáticamente si no se define `DATABASE_URL`; si existe `DATABASE_URL`,
conecta al PostgreSQL/Supabase configurado.
"""
import os

import dj_database_url

from .base import *  # noqa: F401, F403

DEBUG = True

DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()
if DATABASE_URL:
    db_cfg = dj_database_url.parse(
        DATABASE_URL,
        conn_max_age=0,
        ssl_require="supabase" in DATABASE_URL,
    )
    if "postgresql" in db_cfg.get("ENGINE", ""):
        db_cfg.setdefault("OPTIONS", {})["options"] = "-c search_path=public,extensions"
    DATABASES = {"default": db_cfg}
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"
