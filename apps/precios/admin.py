"""Registro de modelos de precios, banners y cargas masivas en el admin técnico."""
from django.contrib import admin

from .models import Banner, CargaMasiva, Precio


@admin.register(Precio)
class PrecioAdmin(admin.ModelAdmin):
    list_display = ("producto", "sucursal", "precio_normal", "precio_oferta", "estado", "fuente", "fecha_observacion")
    list_filter = ("estado", "fuente", "alerta_variacion")
    search_fields = ("producto__nombre", "sucursal__comercio__nombre_fantasia")


@admin.register(Banner)
class BannerAdmin(admin.ModelAdmin):
    list_display = ("titulo", "tipo", "orden", "activo", "desde", "hasta")
    list_filter = ("tipo", "activo")


@admin.register(CargaMasiva)
class CargaMasivaAdmin(admin.ModelAdmin):
    list_display = ("id", "nombre_archivo", "usuario", "estado", "filas_ok", "filas_error", "creado_en")
    list_filter = ("estado",)
