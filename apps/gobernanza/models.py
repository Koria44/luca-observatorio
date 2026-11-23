"""
Modelos de Gobernanza, Habilitación para Publicar Precios, Historial Funcional de Estados,
Sanciones, Apelaciones, Kill Switch, Elevación Temporal de Superadmin y Notificaciones
(# Prompt 7 y Prompt 8).
"""
from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.db import models
from django.utils import timezone

from apps.catalogo.models import Categoria, Producto
from apps.comercios.models import Comercio, Sucursal


class HistorialEstado(models.Model):
    """
    Línea de tiempo funcional de cambios de estado de un comercio, habilitación o precio
    (# Prompt 8 Sección 3.2). Visible para el titular (sus propios casos) y staff operativo.
    # SEGURIDAD: NO almacena IP, user-agent, detalles técnicos ni valores internos de auditoría.
    """

    modelo = models.CharField("Entidad", max_length=40, db_index=True)
    objeto_id = models.CharField("ID entidad", max_length=64, db_index=True)
    estado_anterior = models.CharField("Estado anterior", max_length=30, blank=True)
    estado_nuevo = models.CharField("Estado nuevo", max_length=30)
    resuelto_por_nombre = models.CharField("Resuelto por", max_length=120, blank=True)
    resuelto_por_cargo = models.CharField("Cargo", max_length=60, blank=True)
    motivo = models.TextField("Motivo", blank=True)
    fecha = models.DateTimeField("Fecha", auto_now_add=True, db_index=True)

    class Meta:
        verbose_name = "Historial funcional de estado"
        verbose_name_plural = "Historiales funcionales de estado"
        ordering = ["-fecha"]
        indexes = [models.Index(fields=["modelo", "objeto_id", "-fecha"])]

    def __str__(self) -> str:
        return f"{self.modelo} #{self.objeto_id}: {self.estado_anterior} -> {self.estado_nuevo}"


class ElevacionSuperadmin(models.Model):
    """
    Elevación temporal explícita (máx. 30 min) para que un SUPERADMIN ejecute una acción
    operativa de negocio (ej. aprobar/revocar habilitación o aplicar sanción) con motivo,
    reautenticación TOTP y correo de control (# Prompt 8 Sección 1.3).
    """

    superadmin = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="elevaciones",
        verbose_name="Superadmin",
    )
    motivo = models.TextField("Motivo obligatorio")
    activa_hasta = models.DateTimeField("Activa hasta", db_index=True)
    revocada = models.BooleanField("Revocada manualmente", default=False)
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Elevación temporal de Superadmin"
        verbose_name_plural = "Elevaciones temporales de Superadmin"
        ordering = ["-creado_en"]

    @property
    def esta_activa(self) -> bool:
        return (not self.revocada) and self.activa_hasta > timezone.now()

    @classmethod
    def activa_para(cls, usuario):
        if not usuario or not getattr(usuario, "is_authenticated", False):
            return None
        return (
            cls.objects.filter(
                superadmin=usuario,
                revocada=False,
                activa_hasta__gt=timezone.now(),
            )
            .order_by("-activa_hasta")
            .first()
        )


class SolicitudControlDualSuperadmin(models.Model):
    """
    Control dual para alta o remoción de una cuenta SUPERADMIN cuando existen >= 2 superadmins
    (# Prompt 8 Sección 4.2).
    """

    class Tipo(models.TextChoices):
        PROMOVER = "PROMOVER", "Promover a Superadmin"
        REVOCAR = "REVOCAR", "Revocar rol Superadmin"

    class Estado(models.TextChoices):
        PENDIENTE = "PENDIENTE", "Pendiente de segunda aprobación"
        APROBADA = "APROBADA", "Aprobada y ejecutada"
        RECHAZADA = "RECHAZADA", "Rechazada"

    tipo = models.CharField(max_length=20, choices=Tipo.choices)
    objetivo = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="solicitudes_superadmin_objetivo"
    )
    solicitada_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="solicitudes_superadmin_creadas"
    )
    aprobada_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="solicitudes_superadmin_aprobadas"
    )
    motivo = models.TextField()
    estado = models.CharField(max_length=20, choices=Estado.choices, default=Estado.PENDIENTE, db_index=True)
    creado_en = models.DateTimeField(auto_now_add=True)
    resuelta_en = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-creado_en"]


class Habilitacion(models.Model):
    """
    Autorización municipal expresa, vigente y revocable para que un comercio publique precios (# Sección 2).
    Regla de oro: tener cuenta activa NO basta; se requiere Habilitacion OTORGADA y vigente.
    """

    class Nivel(models.IntegerChoices):
        SIN_HABILITACION = 0, "Nivel 0 · Sin habilitación"
        SUPERVISADO = 1, "Nivel 1 · Supervisado (todo precio pasa por revisión)"
        CONFIABLE = 2, "Nivel 2 · Confiable (autopublicación con muestreo)"

    class Estado(models.TextChoices):
        SOLICITADA = "SOLICITADA", "Solicitada"
        EN_REVISION = "EN_REVISION", "En revisión"
        OBSERVADA = "OBSERVADA", "Observada (requiere corrección)"
        OTORGADA = "OTORGADA", "Otorgada (vigente)"
        RECHAZADA = "RECHAZADA", "Rechazada"
        SUSPENDIDA = "SUSPENDIDA", "Suspendida"
        REVOCADA = "REVOCADA", "Revocada"
        VENCIDA = "VENCIDA", "Vencida"

    comercio = models.ForeignKey(
        Comercio, on_delete=models.CASCADE, related_name="habilitaciones", verbose_name="Comercio"
    )
    nivel = models.PositiveSmallIntegerField("Nivel de confianza", choices=Nivel.choices, default=Nivel.SIN_HABILITACION)
    estado = models.CharField("Estado", max_length=20, choices=Estado.choices, default=Estado.SOLICITADA, db_index=True)
    categorias_autorizadas = models.ManyToManyField(
        Categoria, blank=True, related_name="habilitaciones_autorizadas", verbose_name="Categorías autorizadas"
    )
    sucursales_autorizadas = models.ManyToManyField(
        Sucursal, blank=True, related_name="habilitaciones_autorizadas", verbose_name="Sucursales autorizadas"
    )

    solicitada_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="habilitaciones_solicitadas"
    )
    revisada_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="habilitaciones_revisadas"
    )
    otorgada_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="habilitaciones_otorgadas"
    )
    revocada_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="habilitaciones_revocadas"
    )
    tomado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="habilitaciones_tomadas"
    )
    tomado_hasta = models.DateTimeField("Bloqueo de toma de caso hasta", null=True, blank=True)

    fecha_otorgamiento = models.DateTimeField("Fecha de otorgamiento", null=True, blank=True)
    vigente_hasta = models.DateField("Vigente hasta", null=True, blank=True, db_index=True)
    fecha_revocacion = models.DateTimeField("Fecha de revocación", null=True, blank=True)
    motivo = models.TextField("Motivo / resolución", blank=True)
    motivo_revocacion = models.TextField("Motivo de revocación o suspensión", blank=True)
    observaciones = models.TextField("Observaciones para el comercio", blank=True)
    checklist = models.JSONField("Lista de verificación del fiscalizador", default=dict, blank=True)

    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Habilitación de comercio"
        verbose_name_plural = "Habilitaciones de comercios"
        ordering = ["-creado_en"]
        indexes = [models.Index(fields=["comercio", "estado", "vigente_hasta"])]

    def __str__(self) -> str:
        return f"{self.comercio.nombre_fantasia} — {self.get_estado_display()} (Nivel {self.nivel})"

    @property
    def esta_vigente(self) -> bool:
        if self.estado != self.Estado.OTORGADA or self.nivel < self.Nivel.SUPERVISADO:
            return False
        if self.vigente_hasta and self.vigente_hasta < timezone.localdate():
            return False
        return True

    def cubre_categoria_y_sucursal(self, categoria_id: int, sucursal_id: int) -> bool:
        """Verifica alcance explícito por categoría y sucursal autorizada (# Sección 2.3)."""
        if not self.esta_vigente:
            return False
        cats = list(self.categorias_autorizadas.values_list("id", flat=True))
        if cats and categoria_id not in cats:
            return False
        sucs = list(self.sucursales_autorizadas.values_list("id", flat=True))
        if sucs and sucursal_id not in sucs:
            return False
        return True


class HistorialHabilitacionQuerySet(models.QuerySet):
    def delete(self):
        raise PermissionDenied("El historial de habilitaciones es inmutable.")

    def update(self, **kwargs):
        raise PermissionDenied("El historial de habilitaciones es inmutable.")


class HistorialHabilitacion(models.Model):
    """Bitácora inmutable de cada transición de una Habilitación (# Sección 2.1 / 4)."""

    habilitacion = models.ForeignKey(
        Habilitacion, on_delete=models.PROTECT, related_name="historial", verbose_name="Habilitación"
    )
    estado_anterior = models.CharField(max_length=20, blank=True)
    estado_nuevo = models.CharField(max_length=20)
    nivel_anterior = models.PositiveSmallIntegerField(default=0)
    nivel_nuevo = models.PositiveSmallIntegerField(default=0)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    motivo = models.TextField(blank=True)
    fecha = models.DateTimeField(auto_now_add=True, db_index=True)

    objects = HistorialHabilitacionQuerySet.as_manager()

    class Meta:
        ordering = ["-fecha"]

    def save(self, *args, **kwargs):
        if self.pk is not None:
            raise PermissionDenied("El historial de habilitaciones no admite modificaciones.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise PermissionDenied("El historial de habilitaciones no puede eliminarse.")


class DocumentoHabilitacion(models.Model):
    """Documento respaldatorio privado asociado a una solicitud de habilitación (# Sección 5.3)."""

    class Tipo(models.TextChoices):
        PATENTE = "PATENTE", "Patente municipal vigente"
        INICIO_ACTIVIDADES = "INICIO_ACTIVIDADES", "Constancia inicio de actividades"
        PODER = "PODER", "Poder / representación legal"
        OTRO = "OTRO", "Otro respaldo"

    habilitacion = models.ForeignKey(Habilitacion, on_delete=models.CASCADE, related_name="documentos")
    tipo = models.CharField(max_length=25, choices=Tipo.choices, default=Tipo.PATENTE)
    numero_documento = models.CharField("Número de documento", max_length=60, blank=True)
    archivo_ruta = models.CharField("Ruta privada del archivo", max_length=255)
    subido_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    creado_en = models.DateTimeField(auto_now_add=True)


class AceptacionDocumento(models.Model):
    """Registro de aceptación de Convenio de colaboración, Términos o Privacidad versionados (# Sección 5.3b)."""

    class TipoDoc(models.TextChoices):
        CONVENIO = "CONVENIO", "Convenio de colaboración (borrador)"
        TERMINOS = "TERMINOS", "Términos de uso (borrador)"
        PRIVACIDAD = "PRIVACIDAD", "Política de privacidad (borrador)"

    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="aceptaciones")
    tipo_documento = models.CharField(max_length=20, choices=TipoDoc.choices)
    version = models.CharField(max_length=20, default="1.0-borrador")
    ip = models.GenericIPAddressField(null=True, blank=True)
    fecha = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-fecha"]


class Sancion(models.Model):
    """Medida gradual interna de la plataforma (# Sección 2.6): Advertencia -> Suspensión -> Revocación."""

    class Tipo(models.TextChoices):
        ADVERTENCIA = "ADVERTENCIA", "Advertencia formal"
        SUSPENSION_TEMPORAL = "SUSPENSION_TEMPORAL", "Suspensión temporal"
        REVOCACION = "REVOCACION", "Revocación de habilitación"

    comercio = models.ForeignKey(Comercio, on_delete=models.CASCADE, related_name="sanciones")
    tipo = models.CharField(max_length=25, choices=Tipo.choices)
    motivo = models.TextField("Motivo")
    evidencia = models.TextField("Evidencia de respaldo", blank=True)
    aplicada_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="sanciones_aplicadas"
    )
    fecha_inicio = models.DateField(default=timezone.localdate)
    fecha_termino = models.DateField(null=True, blank=True)
    activa = models.BooleanField(default=True, db_index=True)
    creado_en = models.DateTimeField(auto_now_add=True)


class Apelacion(models.Model):
    """Descargos/apelación de un comercio revisada por un funcionario distinto del sancionador (# Sección 2.6)."""

    class Estado(models.TextChoices):
        PENDIENTE = "PENDIENTE", "Pendiente de resolución"
        ACOGIDA = "ACOGIDA", "Acogida"
        RECHAZADA = "RECHAZADA", "Rechazada"

    sancion = models.ForeignKey(Sancion, on_delete=models.CASCADE, related_name="apelaciones")
    presentada_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    descargos = models.TextField("Descargos del comercio")
    estado = models.CharField(max_length=20, choices=Estado.choices, default=Estado.PENDIENTE, db_index=True)
    resuelta_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="apelaciones_resueltas"
    )
    resolucion = models.TextField(blank=True)
    fecha_resolucion = models.DateTimeField(null=True, blank=True)
    creado_en = models.DateTimeField(auto_now_add=True)


class ConfiguracionObservatorio(models.Model):
    """Parámetros globales y kill switch administrados por DIDESE (# Sección 2.7 / 7)."""

    kill_switch_global = models.BooleanField("Pausar todas las publicaciones nuevas", default=False)
    kill_switch_motivo = models.TextField("Motivo del interruptor general", blank=True)
    comercios_pausados = models.JSONField("IDs de comercios pausados", default=list, blank=True)
    umbral_variacion_pct = models.PositiveSmallIntegerField("Umbral variación atípica (%)", default=40)
    tasa_muestreo_nivel2_pct = models.PositiveSmallIntegerField("Muestreo aleatorio Nivel 2 (%)", default=10)
    dias_obsolescencia = models.PositiveSmallIntegerField("Días para marcar precio obsoleto", default=30)
    actualizado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    @classmethod
    def obtener(cls) -> "ConfiguracionObservatorio":
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


class SolicitudProducto(models.Model):
    """Propuesta de producto nuevo enviada por comercio; requiere revisión municipal (# Sección 5.6)."""

    class Estado(models.TextChoices):
        PENDIENTE = "PENDIENTE", "Pendiente de revisión"
        APROBADA = "APROBADA", "Aprobada y creada en catálogo"
        RECHAZADA = "RECHAZADA", "Rechazada"

    comercio = models.ForeignKey(Comercio, on_delete=models.CASCADE, related_name="solicitudes_producto")
    solicitado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    nombre = models.CharField(max_length=150)
    marca_texto = models.CharField("Marca propuesta", max_length=100, blank=True)
    codigo_barras = models.CharField("Código EAN", max_length=32, blank=True)
    categoria = models.ForeignKey(Categoria, on_delete=models.PROTECT)
    contenido = models.DecimalField(max_digits=10, decimal_places=2)
    unidad_medida = models.CharField(max_length=5, default="un")
    estado = models.CharField(max_length=20, choices=Estado.choices, default=Estado.PENDIENTE, db_index=True)
    revisado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="solicitudes_prod_revisadas"
    )
    motivo_decision = models.TextField(blank=True)
    producto_creado = models.ForeignKey(Producto, on_delete=models.SET_NULL, null=True, blank=True)
    creado_en = models.DateTimeField(auto_now_add=True)


class Notificacion(models.Model):
    """Centro de notificaciones internas por cambio de estado (# Sección 7)."""

    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notificaciones")
    titulo = models.CharField(max_length=160)
    mensaje = models.TextField()
    enlace = models.CharField(max_length=255, blank=True)
    leida = models.BooleanField(default=False, db_index=True)
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-creado_en"]
