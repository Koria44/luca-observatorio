"""
Modelo de usuario personalizado de Luca — Observatorio de Precios (PAC).

# REQ-08: Roles diferenciados (VECINO, COMERCIANTE, FISCALIZADOR, ADMIN) y flujo
# obligatorio de verificación y aprobación para comerciantes:
# PENDIENTE -> VERIFICADA (fiscalizador) -> ACTIVA (administrador DIDESE).
# SEGURIDAD: Login por correo normalizado a minúsculas; el superuser no se usa para operar.
"""
import uuid

from django.conf import settings
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.core.mail import send_mail
from django.db import models
from django.utils import timezone

from apps.nucleo.validadores import (
    formatear_rut,
    normalizar_correo,
    normalizar_rut,
    normalizar_telefono_cl,
    validar_rut,
    validar_telefono_cl,
)


class UsuarioManager(BaseUserManager):
    """Manager personalizado para crear usuarios con correo normalizado."""

    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError("El correo electrónico es obligatorio.")
        email_limpio = normalizar_correo(email)
        if extra_fields.get("rut"):
            extra_fields["rut"] = normalizar_rut(extra_fields["rut"])
        if extra_fields.get("telefono"):
            extra_fields["telefono"] = normalizar_telefono_cl(extra_fields["telefono"])

        usuario = self.model(email=email_limpio, **extra_fields)
        usuario.set_password(password)
        usuario.save(using=self._db)
        return usuario

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("rol", Usuario.Rol.SUPERADMIN)
        extra_fields.setdefault("estado_cuenta", Usuario.EstadoCuenta.ACTIVA)
        return self.create_user(email, password, **extra_fields)


class Usuario(AbstractBaseUser, PermissionsMixin):
    """Usuario de la plataforma Luca con clave primaria UUID y exactamente 5 roles (# Prompt 8)."""

    class Rol(models.TextChoices):
        VECINO = "VECINO", "Vecino/a"
        COMERCIANTE = "COMERCIANTE", "Comerciante"
        FISCALIZADOR = "FISCALIZADOR", "Fiscalizador municipal"
        ADMIN = "ADMIN", "Admin DIDESE"
        SUPERADMIN = "SUPERADMIN", "Superadmin"

    class EstadoCuenta(models.TextChoices):
        PENDIENTE_CORREO = "PENDIENTE_CORREO", "Pendiente de verificación de correo"
        PENDIENTE = "PENDIENTE", "Pendiente de revisión"
        VERIFICADA = "VERIFICADA", "Verificada por fiscalizador"
        ACTIVA = "ACTIVA", "Activa"
        RECHAZADA = "RECHAZADA", "Rechazada"
        SUSPENDIDA = "SUSPENDIDA", "Suspendida"
        BAJA = "BAJA", "Dada de baja (anonimizada)"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField("Correo electrónico", unique=True, db_index=True)
    nombres = models.CharField("Nombres", max_length=120)
    apellidos = models.CharField("Apellidos", max_length=120)
    rut = models.CharField(
        "RUT",
        max_length=12,
        unique=True,
        validators=[validar_rut],
        db_index=True,
    )
    telefono = models.CharField(
        "Teléfono",
        max_length=15,
        validators=[validar_telefono_cl],
    )
    rol = models.CharField("Rol", max_length=20, choices=Rol.choices, default=Rol.VECINO, db_index=True)
    estado_cuenta = models.CharField(
        "Estado de cuenta",
        max_length=20,
        choices=EstadoCuenta.choices,
        default=EstadoCuenta.ACTIVA,
        db_index=True,
    )
    motivo_rechazo = models.TextField("Motivo de rechazo o suspensión", blank=True)

    # Trazabilidad de revisión de comerciantes
    verificada_por = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="cuentas_verificadas",
        verbose_name="Verificada por",
    )
    aprobada_por = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="cuentas_aprobadas",
        verbose_name="Aprobada por",
    )
    fecha_verificacion = models.DateTimeField("Fecha de verificación", null=True, blank=True)
    fecha_aprobacion = models.DateTimeField("Fecha de aprobación", null=True, blank=True)
    ultimo_acceso = models.DateTimeField("Último acceso", null=True, blank=True)

    # Datos opcionales iniciales del local guardados durante el registro paso a paso
    datos_registro_comercio = models.JSONField(
        "Datos de solicitud de comercio", default=dict, blank=True
    )

    # Verificación de correo y TOTP 2FA (# Prompt 7 Sección 1.4 y 5.1)
    correo_verificado = models.BooleanField("Correo verificado", default=True)
    token_verificacion_correo = models.CharField("Token verificación correo", max_length=64, blank=True)
    token_verificacion_expira = models.DateTimeField("Expiración token correo", null=True, blank=True)
    totp_secreto = models.CharField("Secreto TOTP (Base32)", max_length=64, blank=True)
    totp_activo = models.BooleanField("Autenticación en dos pasos (TOTP) activa", default=False)
    codigos_recuperacion = models.JSONField("Códigos de recuperación TOTP (hash)", default=list, blank=True)

    is_active = models.BooleanField("Activo en Django", default=True)
    is_staff = models.BooleanField("Acceso al panel técnico", default=False)
    creado_en = models.DateTimeField("Creado en", auto_now_add=True)
    actualizado_en = models.DateTimeField("Actualizado en", auto_now=True)

    objects = UsuarioManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["nombres", "apellidos", "rut", "telefono"]

    class Meta:
        verbose_name = "Usuario"
        verbose_name_plural = "Usuarios"
        ordering = ["-creado_en"]
        indexes = [
            models.Index(fields=["rol", "estado_cuenta"]),
        ]

    def __str__(self) -> str:
        return f"{self.nombre_completo} ({self.get_rol_display()})"

    def save(self, *args, **kwargs):
        if self.email:
            self.email = normalizar_correo(self.email)
        if self.rut:
            self.rut = normalizar_rut(self.rut)
        if self.telefono:
            self.telefono = normalizar_telefono_cl(self.telefono)
        super().save(*args, **kwargs)

    @property
    def nombre_completo(self) -> str:
        return f"{self.nombres} {self.apellidos}".strip()

    @property
    def rut_formateado(self) -> str:
        return formatear_rut(self.rut)

    @property
    def rut_enmascarado(self) -> str:
        """Enmascara el RUT en listados internos (# SEGURIDAD / Ley 19.628)."""
        if not self.rut or "-" not in self.rut:
            return "***"
        cuerpo, dv = self.rut.split("-", 1)
        return f"**.***.{cuerpo[-3:]}-{dv}"

    @property
    def es_staff_observatorio(self) -> bool:
        return self.rol in (self.Rol.FISCALIZADOR, self.Rol.ADMIN, self.Rol.SUPERADMIN) or self.is_superuser

    @property
    def es_superadmin(self) -> bool:
        return self.rol == self.Rol.SUPERADMIN or self.is_superuser

    def anonimizar_baja(self) -> None:
        """Anonimiza datos personales al dar de baja la cuenta conservando integridad de auditoría (# Sección 8)."""
        sufijo = str(self.id).split("-")[0]
        self.email = f"baja-{sufijo}@anonimizado.luca-pac.cl"
        self.nombres = "Usuario"
        self.apellidos = "Anonimizado"
        self.telefono = "+56900000000"
        self.estado_cuenta = self.EstadoCuenta.BAJA
        self.is_active = False
        self.totp_activo = False
        self.totp_secreto = ""
        self.codigos_recuperacion = []
        self.set_unusable_password()
        self.save()

    def _notificar_cambio_estado(self, asunto: str, cuerpo: str) -> None:
        """Envía correo informativo al comerciante ante cada cambio de estado (# II.5)."""
        send_mail(
            subject=f"[Luca PAC] {asunto}",
            message=cuerpo,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[self.email],
            fail_silently=True,
        )

    def marcar_verificada(self, fiscalizador) -> None:
        """Paso 1 de aprobación: un fiscalizador verifica antecedentes del comerciante."""
        self.estado_cuenta = self.EstadoCuenta.VERIFICADA
        self.verificada_por = fiscalizador
        self.fecha_verificacion = timezone.now()
        self.motivo_rechazo = ""
        self.save(update_fields=["estado_cuenta", "verificada_por", "fecha_verificacion", "motivo_rechazo", "actualizado_en"])
        self._notificar_cambio_estado(
            "Tus datos fueron verificados",
            f"Hola {self.nombres},\n\nUn fiscalizador municipal verificó los antecedentes de tu comercio. "
            "Ahora tu cuenta pasó a revisión final por administración DIDESE. Te avisaremos apenas esté activa.\n\nEquipo Luca — Pedro Aguirre Cerda.",
        )

    def aprobar_cuenta(self, administrador) -> None:
        """Paso 2 (final): un administrador DIDESE activa la cuenta del comerciante."""
        self.estado_cuenta = self.EstadoCuenta.ACTIVA
        self.aprobada_por = administrador
        self.fecha_aprobacion = timezone.now()
        self.motivo_rechazo = ""
        self.save(update_fields=["estado_cuenta", "aprobada_por", "fecha_aprobacion", "motivo_rechazo", "actualizado_en"])
        self._notificar_cambio_estado(
            "¡Tu cuenta de comerciante ya está activa!",
            f"Hola {self.nombres},\n\nTu cuenta en Luca fue aprobada por DIDESE. Ya puedes ingresar "
            "para gestionar tus sucursales y publicar precios y ofertas.\n\nEquipo Luca — Pedro Aguirre Cerda.",
        )

    def rechazar_cuenta(self, revisor, motivo: str) -> None:
        """Rechaza una solicitud con motivo obligatorio."""
        if not motivo or not motivo.strip():
            raise ValueError("Debes indicar un motivo claro para rechazar la cuenta.")
        self.estado_cuenta = self.EstadoCuenta.RECHAZADA
        self.motivo_rechazo = motivo.strip()
        if revisor.rol == self.Rol.FISCALIZADOR:
            self.verificada_por = revisor
            self.fecha_verificacion = timezone.now()
        else:
            self.aprobada_por = revisor
            self.fecha_aprobacion = timezone.now()
        self.save(update_fields=["estado_cuenta", "motivo_rechazo", "verificada_por", "aprobada_por", "fecha_verificacion", "fecha_aprobacion", "actualizado_en"])
        self._notificar_cambio_estado(
            "Resultado de tu solicitud en Luca",
            f"Hola {self.nombres},\n\nTu solicitud de cuenta de comerciante no pudo ser aprobada por el siguiente motivo:\n"
            f"- {self.motivo_rechazo}\n\nSi necesitas corregir tus datos, escríbenos desde la sección Contacto.\n\nEquipo Luca.",
        )
