"""
Modelo de Registro de Auditoría estrictamente inmutable (solo inserción) (# REQ-15).

# SEGURIDAD: Ni la aplicación ni el admin de Django pueden modificar o eliminar
registros de auditoría existentes.
"""
import hashlib
import json

from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.db import models


class AuditoriaQuerySet(models.QuerySet):
    """Impide actualizaciones o eliminaciones masivas sobre registros de auditoría."""

    def delete(self):
        raise PermissionDenied("Los registros de auditoría son inmutables y no pueden eliminarse.")

    def update(self, **kwargs):
        raise PermissionDenied("Los registros de auditoría son inmutables y no pueden modificarse.")


class RegistroAuditoria(models.Model):
    """Bitácora inmutable de acciones críticas en la plataforma Luca."""

    class Accion(models.TextChoices):
        CREAR = "CREAR", "Crear"
        MODIFICAR = "MODIFICAR", "Modificar"
        APROBAR = "APROBAR", "Aprobar"
        RECHAZAR = "RECHAZAR", "Rechazar"
        ELIMINAR = "ELIMINAR", "Eliminar"
        LOGIN = "LOGIN", "Inicio de sesión"
        LOGOUT = "LOGOUT", "Cierre de sesión"
        LOGIN_FALLIDO = "LOGIN_FALLIDO", "Intento fallido de acceso"
        EXPORTAR = "EXPORTAR", "Exportar reporte"
        CARGA = "CARGA", "Carga masiva"
        DENEGADO = "DENEGADO", "Acceso o acción denegada"
        SANCION = "SANCION", "Sanción o suspensión"
        HABILITACION = "HABILITACION", "Cambio de habilitación"
        VER_DOCUMENTO = "VER_DOCUMENTO", "Acceso a documento privado"
        BAJA = "BAJA", "Baja y anonimización"

    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="eventos_auditoria",
        verbose_name="Usuario",
    )
    accion = models.CharField("Acción", max_length=20, choices=Accion.choices, db_index=True)
    modelo = models.CharField("Modelo / Recurso", max_length=80, db_index=True)
    objeto_id = models.CharField("ID del objeto", max_length=64, blank=True)
    valores_anteriores = models.JSONField("Valores anteriores", default=dict, blank=True)
    valores_nuevos = models.JSONField("Valores nuevos", default=dict, blank=True)
    ip = models.GenericIPAddressField("Dirección IP", null=True, blank=True)
    user_agent = models.CharField("Agente de usuario", max_length=255, blank=True)
    motivo = models.TextField("Motivo / justificación", blank=True)
    hash_anterior = models.CharField("Hash registro anterior", max_length=64, blank=True, default="")
    hash_actual = models.CharField("Hash encadenado SHA-256", max_length=64, blank=True, default="", db_index=True)
    fecha = models.DateTimeField("Fecha y hora", auto_now_add=True, db_index=True)

    objects = AuditoriaQuerySet.as_manager()

    class Meta:
        verbose_name = "Registro de auditoría"
        verbose_name_plural = "Registros de auditoría"
        ordering = ["-fecha"]
        indexes = [
            models.Index(fields=["modelo", "accion", "fecha"]),
        ]

    def __str__(self) -> str:
        quien = self.usuario.email if self.usuario else "Sistema"
        return f"[{self.fecha:%Y-%m-%d %H:%M}] {quien} — {self.accion} {self.modelo}#{self.objeto_id}"

    def calcular_hash(self) -> str:
        """Calcula hash SHA-256 determinista encadenado al registro anterior (# Sección 8)."""
        payload = json.dumps(
            {
                "prev": self.hash_anterior or "",
                "usuario": str(self.usuario_id or ""),
                "accion": self.accion,
                "modelo": self.modelo,
                "objeto_id": self.objeto_id,
                "ant": self.valores_anteriores,
                "nvo": self.valores_nuevos,
                "motivo": self.motivo,
            },
            sort_keys=True,
            ensure_ascii=False,
            default=str,
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def save(self, *args, **kwargs):
        # SEGURIDAD / REQ-15: Solo se permite inserción; prohibido actualizar filas existentes
        if self.pk is not None:
            raise PermissionDenied("Un registro de auditoría no puede modificarse una vez creado.")
        ultimo = RegistroAuditoria.objects.order_by("-id").values_list("hash_actual", flat=True).first()
        self.hash_anterior = ultimo or "GENESIS"
        self.hash_actual = self.calcular_hash()
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        # SEGURIDAD / REQ-15: Prohibido eliminar registros de auditoría
        raise PermissionDenied("Un registro de auditoría no puede eliminarse.")
