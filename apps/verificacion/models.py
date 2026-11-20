"""
Modelo persistente para la lista de verificación oficial de los 16 requerimientos de Luca.

Reemplaza la lista HTML estática cuyas casillas no se guardaban, exigiendo evidencia real
antes de marcar un requerimiento como `CUMPLIDO`.
"""
from django.conf import settings
from django.db import models


class VerificacionRequisito(models.Model):
    """Estado verificado y trazable de cada uno de los 16 requerimientos del observatorio."""

    class Estado(models.TextChoices):
        PENDIENTE = "PENDIENTE", "Pendiente"
        CUMPLIDO = "CUMPLIDO", "Cumplido (con evidencia)"

    numero = models.PositiveSmallIntegerField("Número (1–16)", unique=True)
    titulo = models.CharField("Requerimiento", max_length=120)
    estado = models.CharField("Estado", max_length=15, choices=Estado.choices, default=Estado.PENDIENTE)
    evidencia = models.TextField("Rutas / enlaces de evidencia", blank=True)
    comentario = models.TextField("Observaciones de verificación", blank=True)
    verificado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True
    )
    fecha = models.DateTimeField("Última actualización", auto_now=True)

    class Meta:
        verbose_name = "Verificación de requerimiento"
        verbose_name_plural = "Verificación de requerimientos (1–16)"
        ordering = ["numero"]

    def __str__(self) -> str:
        return f"REQ-{self.numero:02d} {self.titulo} [{self.estado}]"
