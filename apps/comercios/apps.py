"""Configuración de la aplicación `comercios`."""
from django.apps import AppConfig


class ComerciosConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.comercios"
    verbose_name = "Comercios y sucursales"
