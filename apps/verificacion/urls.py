"""Rutas de verificación de requerimientos."""
from django.urls import path

from . import views

app_name = "verificacion"

urlpatterns = [
    path("", views.lista_verificacion, name="lista"),
    path("<int:numero>/actualizar/", views.actualizar_requisito, name="actualizar"),
]
