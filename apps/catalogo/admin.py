"""Registro de modelos del catálogo en el admin de Django."""
from django.contrib import admin

from .models import Categoria, Marca, Producto


@admin.register(Categoria)
class CategoriaAdmin(admin.ModelAdmin):
    list_display = ("nombre", "slug", "icono", "orden", "activa")
    prepopulated_fields = {"slug": ("nombre",)}


@admin.register(Marca)
class MarcaAdmin(admin.ModelAdmin):
    search_fields = ("nombre",)


@admin.register(Producto)
class ProductoAdmin(admin.ModelAdmin):
    list_display = ("nombre_completo", "categoria", "formato", "es_canasta_basica", "es_estrella", "activo")
    list_filter = ("categoria", "es_canasta_basica", "es_estrella", "activo")
    search_fields = ("nombre", "marca__nombre", "codigo_barras")
