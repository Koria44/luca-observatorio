"""Configuración de la aplicación `nucleo`."""
from django.apps import AppConfig


class NucleoConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.nucleo"
    verbose_name = "Núcleo y utilidades"
