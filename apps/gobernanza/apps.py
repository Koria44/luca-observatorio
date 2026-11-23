"""Configuración de la app de gobernanza de Luca."""
from django.apps import AppConfig


class GobernanzaConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.gobernanza"
    verbose_name = "Gobernanza y Controles"
