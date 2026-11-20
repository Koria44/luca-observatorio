"""Rutas del catálogo maestro (# REQ-01)."""
from django.urls import path

from . import imagenes_views, views

app_name = "catalogo"

urlpatterns = [
    path("", views.lista_productos, name="lista"),
    path("nuevo/", views.crear_producto, name="crear"),
    path("<int:pk>/editar/", views.editar_producto, name="editar"),
    path("producto/<int:producto_id>/subir-foto/", imagenes_views.vista_subir_foto_producto, name="subir_foto"),
    path("imagenes/revision/", imagenes_views.vista_cola_revision_imagenes, name="cola_imagenes"),
    path("imagenes/<int:imagen_id>/decidir/", imagenes_views.vista_decidir_imagen_producto, name="decidir_imagen"),
    path("imagenes/logo/<int:comercio_id>/decidir/", imagenes_views.vista_decidir_logo_comercio, name="decidir_logo"),
    path("imagenes/<int:imagen_id>/reportar/", imagenes_views.vista_reportar_imagen, name="reportar_imagen"),
    path("imagenes/pendiente/<path:ruta>", imagenes_views.vista_servir_imagen_pendiente, name="ver_pendiente"),
    path("api/ean/<str:codigo>/", views.api_buscar_por_ean, name="api_buscar_ean"),
]
