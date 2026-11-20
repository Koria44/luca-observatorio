"""Rutas públicas del portal ciudadano de Luca."""
from django.urls import path

from . import canasta_views, views

app_name = "portal"

urlpatterns = [
    path("", views.vista_inicio, name="inicio"),
    path("buscar/", views.vista_buscar, name="buscar"),
    path("comparar/<int:producto_id>/", views.vista_comparar_producto, name="comparar"),
    path("ofertas/", views.vista_ofertas, name="ofertas"),
    path("mapa/", views.vista_mapa_comercios, name="mapa"),
    path("comercio/<int:sucursal_id>/", views.vista_detalle_sucursal, name="detalle_sucursal"),
    path("mi-canasta/", canasta_views.vista_mi_canasta, name="mi_canasta"),
    path("api/canasta/agregar/", canasta_views.api_agregar_item_canasta, name="api_agregar_canasta"),
    path("api/canasta/calcular/", canasta_views.api_calcular_canasta, name="api_calcular_canasta"),
    path("mi-canasta/alertas/", canasta_views.vista_alertas_precio, name="alertas_precio"),
    path("ferias-hoy/", canasta_views.vista_ferias_hoy, name="ferias_hoy"),
    path("precios/<int:precio_id>/reportar/", canasta_views.vista_reportar_precio, name="reportar_precio"),
    path("transparencia/", views.vista_transparencia, name="transparencia"),
    path("preguntas-frecuentes/", views.vista_faq, name="faq"),
    path("contacto/", views.vista_contacto, name="contacto"),
    path("privacidad/", views.vista_privacidad, name="privacidad"),
]
