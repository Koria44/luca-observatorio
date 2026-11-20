"""Rutas de exportación Excel y PDF (# REQ-14)."""
from django.urls import path

from . import views

app_name = "reportes"

urlpatterns = [
    path("excel/", views.exportar_excel, name="excel"),
    path("pdf/", views.exportar_pdf, name="pdf"),
    path("afiche-qr/<int:comercio_id>/", views.exportar_afiche_qr, name="afiche_qr"),
    path("boletin-semanal/", views.exportar_boletin_semanal, name="boletin_semanal"),
]
