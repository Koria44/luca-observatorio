"""Rutas de paneles por rol (# REQ-07, REQ-08)."""
from django.urls import path

from . import views

app_name = "panel"

urlpatterns = [
    path("", views.vista_panel_inicio, name="inicio"),
    path("admin/", views.vista_dashboard_admin, name="admin"),
    path("admin/cobertura/", views.vista_cobertura_didese, name="cobertura_didese"),
    path("fiscalizador/", views.vista_dashboard_fiscalizador, name="fiscalizador"),
    path("comerciante/", views.vista_dashboard_comerciante, name="comerciante"),
]
