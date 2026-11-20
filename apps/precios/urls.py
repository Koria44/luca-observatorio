"""Rutas de gestión de precios, revisión municipal y cron (# REQ-03, 06, 09)."""
from django.urls import path

from . import carga_masiva, views

app_name = "precios"

urlpatterns = [
    path("registrar/", views.vista_registrar_precio, name="registrar"),
    path("terreno/", views.vista_registro_terreno, name="terreno"),
    path("mis-precios/", views.vista_mis_precios, name="mis_precios"),
    path("revision/", views.vista_cola_revision_precios, name="cola_revision"),
    path("revision/<int:pk>/decidir/", views.vista_decidir_precio, name="decidir"),
    path("reportes/<int:pk>/atender/", views.vista_atender_reporte_precio, name="atender_reporte"),
    path("<int:pk>/confirmar-vigencia/", views.vista_confirmar_vigencia, name="confirmar_vigencia"),
    path("cron/expirar/", views.vista_cron_expirar_ofertas, name="cron_expirar"),
    path("carga-masiva/", carga_masiva.vista_carga_masiva, name="carga_masiva"),
    path("carga-masiva/plantilla/", carga_masiva.descargar_plantilla_carga, name="plantilla_carga"),
]
