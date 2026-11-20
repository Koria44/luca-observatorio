"""Rutas de gestión de comercios y sucursales (# REQ-02)."""
from django.urls import path

from apps.catalogo.imagenes_views import vista_subir_logo_comercio

from . import views

app_name = "comercios"

urlpatterns = [
    path("mis-sucursales/", views.mis_sucursales, name="mis_sucursales"),
    path("sucursal/<int:pk>/editar/", views.editar_sucursal, name="editar_sucursal"),
    path("nuevo/", views.crear_comercio, name="crear_comercio"),
    path("<int:comercio_id>/logo/", vista_subir_logo_comercio, name="subir_logo"),
]
