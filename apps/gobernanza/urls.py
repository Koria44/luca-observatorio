"""Rutas exclusivas del Panel Superadmin (`/superadmin/`) (# Prompt 8 Sección 4)."""
from django.urls import path

from . import superadmin_views

app_name = "superadmin"

urlpatterns = [
    path("", superadmin_views.panel_superadmin, name="panel"),
    path("elevacion/", superadmin_views.accion_elevacion, name="elevacion"),
    path("usuarios/<uuid:usuario_id>/rol/", superadmin_views.accion_cambiar_rol, name="cambiar_rol"),
    path("usuarios/<uuid:usuario_id>/cerrar-sesiones/", superadmin_views.accion_cerrar_sesiones, name="cerrar_sesiones"),
    path("kill-switch/", superadmin_views.accion_kill_switch, name="kill_switch"),
]
