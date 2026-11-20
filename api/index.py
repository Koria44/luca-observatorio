"""
Punto de entrada WSGI para despliegue serverless en Vercel.
Vercel busca el objeto `app` en `api/index.py`.
"""
import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.produccion")
app = get_wsgi_application()
