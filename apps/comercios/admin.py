"""Registro de comercios y sucursales en el admin técnico de Django."""
from django.contrib import admin

from .models import Comercio, Sucursal


class SucursalInline(admin.TabularInline):
    model = Sucursal
    extra = 0


@admin.register(Comercio)
class ComercioAdmin(admin.ModelAdmin):
    list_display = ("nombre_fantasia", "tipo", "estado", "comercio_confiable", "activo")
    list_filter = ("tipo", "estado", "activo", "comercio_confiable")
    search_fields = ("nombre_fantasia", "razon_social", "rut")
    inlines = [SucursalInline]


@admin.register(Sucursal)
class SucursalAdmin(admin.ModelAdmin):
    list_display = ("nombre_visible", "direccion", "sector", "activa", "verificada_mapa")
    list_filter = ("sector", "activa", "verificada_mapa")
    search_fields = ("nombre", "direccion", "comercio__nombre_fantasia")
