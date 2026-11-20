"""Registro del modelo `Usuario` en el admin técnico de Django."""
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import Usuario


@admin.register(Usuario)
class UsuarioAdmin(BaseUserAdmin):
    list_display = ("email", "nombre_completo", "rut_enmascarado", "rol", "estado_cuenta", "creado_en")
    list_filter = ("rol", "estado_cuenta", "is_active")
    search_fields = ("email", "nombres", "apellidos", "rut")
    ordering = ("-creado_en",)

    fieldsets = (
        ("Acceso", {"fields": ("email", "password")}),
        ("Datos personales", {"fields": ("nombres", "apellidos", "rut", "telefono")}),
        ("Rol y estado", {"fields": ("rol", "estado_cuenta", "motivo_rechazo")}),
        ("Revisión", {"fields": ("verificada_por", "fecha_verificacion", "aprobada_por", "fecha_aprobacion")}),
        ("Permisos técnicos", {"fields": ("is_active", "is_staff", "is_superuser")}),
    )
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("email", "nombres", "apellidos", "rut", "telefono", "rol", "estado_cuenta", "password1", "password2"),
            },
        ),
    )
