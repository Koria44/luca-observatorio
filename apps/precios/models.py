"""
Modelos de Precios (inmutables), Banners y Carga Masiva (# REQ-03, 06, 09, 10, 13).

Diseño clave (# REQ-06):
Actualizar un precio crea una fila nueva apuntando vía `reemplaza` al registro anterior,
el cual pasa a estado `REEMPLAZADO`. Así el historial completo jamás se pierde.

Diseño clave (# REQ-09):
La vigencia de las ofertas se evalúa siempre en la consulta (`vigentes()`), de modo que
las ofertas vencidas desaparecen automáticamente aunque no haya corrido el cron.
"""
from decimal import Decimal

from django.conf import settings
from django.db import models
from django.db.models import F, Q
from django.utils import timezone

from apps.catalogo.models import Producto
from apps.comercios.models import Sucursal
from apps.nucleo.validadores import validar_precio_clp


class PrecioQuerySet(models.QuerySet):
    """Consultas reutilizables para precios publicados y vigentes (# REQ-04, REQ-09)."""

    def publicados(self):
        return self.filter(
            estado=Precio.Estado.PUBLICADO,
            producto__activo=True,
            sucursal__activa=True,
            sucursal__comercio__activo=True,
            sucursal__comercio__estado="ACTIVO",
        )

    def vigentes(self, fecha=None):
        hoy = fecha or timezone.localdate()
        return self.publicados().filter(
            vigencia_desde__lte=hoy,
        ).filter(
            Q(vigencia_hasta__isnull=True) | Q(vigencia_hasta__gte=hoy)
        )

    def ofertas_vigentes(self, fecha=None):
        return self.vigentes(fecha=fecha).filter(precio_oferta__isnull=False)


class Precio(models.Model):
    """Registro inmutable de precio y/o promoción de un producto en una sucursal."""

    class Fuente(models.TextChoices):
        COMERCIANTE = "COMERCIANTE", "Informado por el comercio"
        FISCALIZADOR = "FISCALIZADOR", "Levantado por fiscalizador"
        CARGA_MASIVA = "CARGA_MASIVA", "Carga masiva verificada"
        API = "API", "Integración externa"
        DEMO_REFERENCIAL = "DEMO_REFERENCIAL", "Dato de demostración basado en precio de referencia"

    class Estado(models.TextChoices):
        BORRADOR = "BORRADOR", "Borrador"
        PENDIENTE = "PENDIENTE", "Pendiente de revisión"
        PUBLICADO = "PUBLICADO", "Publicado"
        RECHAZADO = "RECHAZADO", "Rechazado"
        REEMPLAZADO = "REEMPLAZADO", "Reemplazado (histórico)"
        VENCIDO = "VENCIDO", "Vencido"

    producto = models.ForeignKey(
        Producto, on_delete=models.PROTECT, related_name="precios", verbose_name="Producto"
    )
    sucursal = models.ForeignKey(
        Sucursal, on_delete=models.PROTECT, related_name="precios", verbose_name="Sucursal"
    )
    precio_normal = models.PositiveIntegerField(
        "Precio normal (CLP)", validators=[validar_precio_clp]
    )
    precio_oferta = models.PositiveIntegerField(
        "Precio de oferta (CLP)", null=True, blank=True, validators=[validar_precio_clp]
    )
    vigencia_desde = models.DateField("Vigente desde", default=timezone.localdate, db_index=True)
    vigencia_hasta = models.DateField("Vigente hasta", null=True, blank=True, db_index=True)

    # Condiciones de la promoción (# REQ-03, REQ-04, REQ-13)
    compra_minima = models.PositiveSmallIntegerField("Compra mínima (unidades)", null=True, blank=True)
    medio_pago = models.CharField("Medio de pago exigido", max_length=80, blank=True)
    requiere_membresia = models.BooleanField("Requiere membresía o club", default=False)
    nombre_membresia = models.CharField("Nombre de membresía", max_length=80, blank=True)
    condiciones = models.TextField("Otras condiciones", blank=True)

    # Transparencia y origen del dato (# REQ-13)
    fuente = models.CharField("Fuente del precio", max_length=25, choices=Fuente.choices, default=Fuente.COMERCIANTE)
    fuente_detalle = models.CharField("Detalle / URL de referencia", max_length=255, blank=True)
    fecha_observacion = models.DateField("Fecha de observación", default=timezone.localdate, db_index=True)
    stock_confirmado = models.BooleanField("Disponibilidad confirmada en local", default=False)

    # Flujo de revisión y trazabilidad (# REQ-06, REQ-09)
    estado = models.CharField("Estado", max_length=20, choices=Estado.choices, default=Estado.PENDIENTE, db_index=True)
    registrado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="precios_registrados",
        verbose_name="Registrado por",
    )
    revisado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="precios_revisados",
        verbose_name="Revisado por",
    )
    fecha_revision = models.DateTimeField("Fecha de revisión", null=True, blank=True)
    motivo_rechazo = models.TextField("Motivo de rechazo", blank=True)
    alerta_variacion = models.BooleanField("Alerta de variación atípica (> ±40 %)", default=False, db_index=True)
    variacion_porcentual = models.DecimalField(
        "Variación respecto al precio anterior (%)", max_digits=7, decimal_places=2, null=True, blank=True
    )
    reemplaza = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reemplazado_por",
        verbose_name="Reemplaza a registro anterior",
    )

    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    objects = PrecioQuerySet.as_manager()

    class Meta:
        verbose_name = "Precio"
        verbose_name_plural = "Precios"
        ordering = ["-fecha_observacion", "-creado_en"]
        constraints = [
            models.CheckConstraint(
                condition=Q(precio_normal__gt=0),
                name="chk_precio_normal_positivo",
            ),
            models.CheckConstraint(
                condition=Q(precio_oferta__isnull=True) | Q(precio_oferta__lt=F("precio_normal")),
                name="chk_precio_oferta_menor_normal",
            ),
            models.CheckConstraint(
                condition=Q(vigencia_hasta__isnull=True) | Q(vigencia_hasta__gte=F("vigencia_desde")),
                name="chk_vigencia_coherente",
            ),
        ]
        indexes = [
            models.Index(fields=["producto", "sucursal", "estado"]),
            models.Index(fields=["estado", "vigencia_desde", "vigencia_hasta"]),
            models.Index(fields=["producto", "fecha_observacion"]),
        ]

    def __str__(self) -> str:
        return f"{self.producto.nombre_completo} @ {self.sucursal.nombre_visible}: ${self.precio_vigente:,}"

    @property
    def precio_vigente(self) -> int:
        """Devuelve el precio de oferta si existe y está vigente; si no, el precio normal."""
        if self.precio_oferta and self.esta_vigente:
            return self.precio_oferta
        return self.precio_normal

    @property
    def esta_vigente(self) -> bool:
        hoy = timezone.localdate()
        if self.estado != self.Estado.PUBLICADO:
            return False
        if self.vigencia_desde and self.vigencia_desde > hoy:
            return False
        if self.vigencia_hasta and self.vigencia_hasta < hoy:
            return False
        return True

    @property
    def es_oferta_activa(self) -> bool:
        return bool(self.precio_oferta and self.esta_vigente)

    @property
    def porcentaje_descuento(self) -> int:
        if not self.precio_oferta or not self.precio_normal:
            return 0
        return round(((self.precio_normal - self.precio_oferta) / self.precio_normal) * 100)

    @property
    def ahorro_clp(self) -> int:
        if not self.precio_oferta:
            return 0
        return max(0, self.precio_normal - self.precio_oferta)

    @property
    def precio_por_unidad(self) -> int:
        """
        Calcula el precio equivalente por kg, litro o unidad (# REQ-01 / REQ-04).
        Permite comparar de forma justa arroz 1 kg vs. 500 g o aceite 900 ml vs. 1 L.
        """
        base = float(self.producto.contenido_base or Decimal("1"))
        if base <= 0:
            return self.precio_vigente
        if self.producto.unidad_medida in ("g", "kg", "ml", "l"):
            return round((self.precio_vigente / base) * 1000)
        return round(self.precio_vigente / base)

    @property
    def es_demo(self) -> bool:
        return self.fuente == self.Fuente.DEMO_REFERENCIAL

    @property
    def etiquetas_condiciones(self) -> list[str]:
        """Lista legible de condiciones de compra para mostrar en el comparador (# REQ-04, REQ-13)."""
        etiquetas = []
        if self.compra_minima and self.compra_minima > 1:
            etiquetas.append(f"Compra mínima {self.compra_minima} un.")
        if self.medio_pago:
            etiquetas.append(f"Solo con {self.medio_pago}")
        if self.requiere_membresia:
            nombre = self.nombre_membresia or "club de socios"
            etiquetas.append(f"Requiere membresía ({nombre})")
        if self.condiciones:
            etiquetas.append(self.condiciones[:80])
        return etiquetas


class Banner(models.Model):
    """Banner del carrusel accesible de la página de inicio (# II.9)."""

    class Tipo(models.TextChoices):
        OFERTA = "OFERTA", "Oferta del momento"
        PRODUCTO_ESTRELLA = "PRODUCTO_ESTRELLA", "Producto estrella"
        INFORMATIVO = "INFORMATIVO", "Aviso informativo"

    titulo = models.CharField("Título", max_length=120)
    subtitulo = models.CharField("Subtítulo", max_length=220)
    tipo = models.CharField("Tipo", max_length=25, choices=Tipo.choices, default=Tipo.OFERTA)
    producto = models.ForeignKey(
        Producto, on_delete=models.SET_NULL, null=True, blank=True, related_name="banners"
    )
    enlace = models.CharField("Enlace destino", max_length=255, default="/ofertas/")
    esquema_color = models.CharField("Esquema de color", max_length=30, default="marino")
    orden = models.PositiveSmallIntegerField("Orden", default=0)
    desde = models.DateField("Visible desde", default=timezone.localdate)
    hasta = models.DateField("Visible hasta", null=True, blank=True)
    activo = models.BooleanField("Activo", default=True)
    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Banner"
        verbose_name_plural = "Banners"
        ordering = ["orden", "-creado_en"]

    def __str__(self) -> str:
        return self.titulo


class CargaMasiva(models.Model):
    """Registro de importaciones masivas CSV/Excel de precios (# REQ-10)."""

    class Estado(models.TextChoices):
        VALIDADA = "VALIDADA", "Validada (en vista previa)"
        CONFIRMADA = "CONFIRMADA", "Confirmada"
        CON_ERRORES = "CON_ERRORES", "Con errores"
        CANCELADA = "CANCELADA", "Cancelada"

    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="cargas_masivas"
    )
    comercio = models.ForeignKey(
        "comercios.Comercio", on_delete=models.SET_NULL, null=True, blank=True, related_name="cargas_masivas"
    )
    nombre_archivo = models.CharField("Nombre del archivo", max_length=255)
    estado = models.CharField("Estado", max_length=20, choices=Estado.choices, default=Estado.VALIDADA)
    filas_total = models.PositiveIntegerField("Total de filas", default=0)
    filas_ok = models.PositiveIntegerField("Filas válidas", default=0)
    filas_error = models.PositiveIntegerField("Filas con error", default=0)
    informe_errores = models.JSONField("Detalle de errores por fila", default=list, blank=True)
    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Carga masiva"
        verbose_name_plural = "Cargas masivas"
        ordering = ["-creado_en"]

    def __str__(self) -> str:
        return f"Carga #{self.id} ({self.nombre_archivo}) — {self.get_estado_display()}"


class ReportePrecio(models.Model):
    """Reporte ciudadano de discrepancia en sala (precio distinto, sin stock, oferta vencida)."""

    class Motivo(models.TextChoices):
        PRECIO_DISTINTO = "PRECIO_DISTINTO", "El precio en el local es distinto"
        SIN_STOCK = "SIN_STOCK", "Producto agotado / sin stock"
        OFERTA_TERMINADA = "OFERTA_TERMINADA", "La oferta ya no estaba vigente"
        OTRO = "OTRO", "Otra observación"

    precio = models.ForeignKey(Precio, on_delete=models.CASCADE, related_name="reportes_ciudadanos")
    motivo = models.CharField("Motivo", max_length=30, choices=Motivo.choices, default=Motivo.PRECIO_DISTINTO)
    comentario = models.CharField("Comentario opcional", max_length=240, blank=True)
    reportado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True
    )
    atendido = models.BooleanField("Atendido por fiscalizador", default=False, db_index=True)
    atendido_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reportes_precio_atendidos",
    )
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Reporte ciudadano de precio"
        verbose_name_plural = "Reportes ciudadanos de precios"
        ordering = ["atendido", "-creado_en"]

    def __str__(self) -> str:
        return f"Reporte #{self.id} sobre {self.precio}"


class CanastaItem(models.Model):
    """Ítem guardado en la lista de compras personal de un vecino autenticado."""

    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="canasta_items")
    producto = models.ForeignKey(Producto, on_delete=models.CASCADE, related_name="en_canastas")
    cantidad = models.PositiveSmallIntegerField("Cantidad", default=1)
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Ítem de canasta personal"
        verbose_name_plural = "Ítems de canasta personal"
        constraints = [
            models.UniqueConstraint(fields=["usuario", "producto"], name="unico_usuario_producto_canasta"),
        ]


class AlertaPrecio(models.Model):
    """Alerta de baja de precio configurada por un vecino registrado."""

    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="alertas_precio")
    producto = models.ForeignKey(Producto, on_delete=models.CASCADE, related_name="alertas")
    precio_objetivo = models.PositiveIntegerField("Avisar cuando baje de (CLP)", validators=[validar_precio_clp])
    sector = models.CharField("Sector preferido (opcional)", max_length=80, blank=True)
    activa = models.BooleanField("Activa", default=True, db_index=True)
    ultima_notificacion = models.DateTimeField("Última notificación enviada", null=True, blank=True)
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Alerta de baja de precio"
        verbose_name_plural = "Alertas de baja de precio"
        ordering = ["-creado_en"]

    def __str__(self) -> str:
        return f"Alerta {self.usuario.email}: {self.producto.nombre} <= ${self.precio_objetivo:,}"
