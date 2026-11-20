"""
Modelos de Comercios, Sucursales y control de consumo API de mapas (# REQ-02, REQ-05, REQ-16).

# ADR-005: `latitud` y `longitud` son la fuente de verdad editable en Django.
En PostgreSQL/Supabase, la migración PostGIS agrega la columna generada
`ubicacion geography(Point,4326)` (NO mapeada en este modelo) junto con su índice GIST.
"""
from django.conf import settings
from django.db import models
from django.db.models import Q

from apps.nucleo.validadores import (
    SECTORES_PAC,
    normalizar_rut,
    normalizar_telefono_cl,
    validar_rut,
    validar_telefono_cl,
)


class Comercio(models.Model):
    """Establecimiento o cadena comercial registrada en el observatorio."""

    class Tipo(models.TextChoices):
        SUPERMERCADO = "SUPERMERCADO", "Supermercado"
        ALMACEN = "ALMACEN", "Almacén de barrio"
        MINIMARKET = "MINIMARKET", "Minimarket"
        FARMACIA = "FARMACIA", "Farmacia"
        FERIA = "FERIA", "Feria libre / Mercado"
        PANADERIA = "PANADERIA", "Panadería"
        CARNICERIA = "CARNICERIA", "Carnicería"
        VERDULERIA = "VERDULERIA", "Verdulería / Frutería"
        OTRO = "OTRO", "Otro"

    class Estado(models.TextChoices):
        PENDIENTE = "PENDIENTE", "Pendiente"
        VERIFICADO = "VERIFICADO", "Verificado"
        ACTIVO = "ACTIVO", "Activo"
        RECHAZADO = "RECHAZADO", "Rechazado"
        SUSPENDIDO = "SUSPENDIDO", "Suspendido"

    class EstadoLogo(models.TextChoices):
        SIN_LOGO = "SIN_LOGO", "Sin logo"
        PENDIENTE = "PENDIENTE", "En revisión"
        APROBADO = "APROBADO", "Aprobado"
        RECHAZADO = "RECHAZADO", "Rechazado"

    razon_social = models.CharField("Razón social", max_length=180)
    nombre_fantasia = models.CharField("Nombre de fantasía", max_length=150, db_index=True)
    rut = models.CharField("RUT del comercio", max_length=12, validators=[validar_rut], db_index=True)
    tipo = models.CharField("Tipo de comercio", max_length=20, choices=Tipo.choices, db_index=True)
    propietario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="comercios",
        verbose_name="Propietario / representante",
    )
    estado = models.CharField(
        "Estado", max_length=20, choices=Estado.choices, default=Estado.PENDIENTE, db_index=True
    )
    comercio_confiable = models.BooleanField(
        "Comercio confiable (publicación directa sin revisión previa)", default=False
    )
    telefono = models.CharField("Teléfono comercial", max_length=15, blank=True, validators=[validar_telefono_cl])
    email = models.EmailField("Correo comercial", blank=True)
    sitio_web = models.URLField("Sitio web", blank=True)
    activo = models.BooleanField("Activo", default=True, db_index=True)

    # Logo del comercio con flujo de aprobación (# REQ-02, REQ-12, Prompt 5 Sección 3)
    logo = models.CharField("Ruta de logo procesado (480px)", max_length=255, blank=True)
    logo_miniatura = models.CharField("Ruta de logo miniatura (240px)", max_length=255, blank=True)
    logo_estado = models.CharField(
        "Estado del logo", max_length=20, choices=EstadoLogo.choices, default=EstadoLogo.SIN_LOGO, db_index=True
    )
    logo_motivo_rechazo = models.TextField("Motivo de rechazo del logo", blank=True)
    logo_revisado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="logos_revisados",
        verbose_name="Logo revisado por",
    )
    logo_fecha_revision = models.DateTimeField("Fecha de revisión del logo", null=True, blank=True)

    # Trazabilidad de la fuente del dato (# REQ-13 / II.10)
    fuente_dato = models.CharField("Fuente del registro", max_length=255, blank=True)
    fecha_verificacion_dato = models.DateField("Fecha de verificación de dirección", null=True, blank=True)

    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Comercio"
        verbose_name_plural = "Comercios"
        ordering = ["nombre_fantasia"]
        indexes = [
            models.Index(fields=["tipo", "estado", "activo"]),
        ]

    def __str__(self) -> str:
        return self.nombre_fantasia

    def save(self, *args, **kwargs):
        if self.rut:
            self.rut = normalizar_rut(self.rut)
        if self.telefono:
            self.telefono = normalizar_telefono_cl(self.telefono)
        super().save(*args, **kwargs)

    @property
    def iniciales_monograma(self) -> str:
        """Devuelve 2 iniciales para mostrar un monograma accesible cuando no hay logo aprobado."""
        palabras = [p for p in self.nombre_fantasia.split() if p.isalnum()]
        if len(palabras) >= 2:
            return (palabras[0][0] + palabras[1][0]).upper()
        return self.nombre_fantasia[:2].upper()

    @property
    def color_monograma(self) -> str:
        paleta = ["#12385C", "#0B6E70", "#C8401C", "#187540", "#1D6FB8"]
        return paleta[(self.pk or 0) % len(paleta)]

    @property
    def clase_color_monograma(self) -> str:
        """Clase Tailwind equivalente para evitar atributos `style` en línea en plantillas HTML."""
        clases = ["bg-marino-700", "bg-turquesa-700", "bg-coral-600", "bg-verde-700", "bg-azul-600"]
        return clases[(self.pk or 0) % len(clases)]

    @property
    def url_logo_publico(self) -> str:
        """Solo expone URL del logo en el portal público cuando está APROBADO (# SEGURIDAD)."""
        if self.logo_estado == self.EstadoLogo.APROBADO and self.logo:
            from apps.nucleo.imagenes import url_publica_imagen

            return url_publica_imagen(self.logo)
        return ""


class Sucursal(models.Model):
    """
    Sucursal física específica con dirección, sector y coordenadas geográficas.
    NOTA PostGIS (# ADR-005): la columna `ubicacion geography(Point,4326)` existe en
    PostgreSQL mediante migración RunSQL y no se mapea en este modelo Django.
    """

    class OrigenCoordenada(models.TextChoices):
        OSM_DEMO = "OSM_DEMO", "Referencia OSM / Demo"
        GEOAPIFY = "GEOAPIFY", "Geocodificador Geoapify"
        MANUAL = "MANUAL", "Ajuste manual por comercio"
        FISCALIZADOR = "FISCALIZADOR", "Confirmado por fiscalizador"

    comercio = models.ForeignKey(
        Comercio, on_delete=models.CASCADE, related_name="sucursales", verbose_name="Comercio"
    )
    nombre = models.CharField("Nombre de sucursal", max_length=150)
    direccion = models.CharField("Dirección", max_length=220)
    direccion_normalizada = models.CharField("Dirección normalizada", max_length=255, blank=True)
    sector = models.CharField("Sector / Población", max_length=80, choices=SECTORES_PAC, db_index=True)
    latitud = models.DecimalField("Latitud", max_digits=9, decimal_places=6)
    longitud = models.DecimalField("Longitud", max_digits=9, decimal_places=6)
    horario = models.CharField("Horario de atención", max_length=160, default="Lun a Sáb 09:00–20:30")
    telefono = models.CharField("Teléfono de sucursal", max_length=15, blank=True)
    activa = models.BooleanField("Activa", default=True, db_index=True)
    verificada_mapa = models.BooleanField("Coordenadas verificadas para mapa público", default=True)

    # Control geográfico y verificación (# Prompt 5 Secciones 1.6 y 2.4)
    fuera_de_comuna = models.BooleanField("Ubicación fuera del límite de Pedro Aguirre Cerda", default=False, db_index=True)
    requiere_ajuste = models.BooleanField("Requiere ajuste manual de pin", default=False)
    origen_coordenada = models.CharField(
        "Origen de coordenada", max_length=20, choices=OrigenCoordenada.choices, default=OrigenCoordenada.OSM_DEMO
    )
    ubicacion_verificada = models.BooleanField("Ubicación verificada en terreno", default=False)
    verificada_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="sucursales_verificadas",
        verbose_name="Ubicación verificada por",
    )
    fecha_verificacion = models.DateTimeField("Fecha de verificación de ubicación", null=True, blank=True)

    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Sucursal"
        verbose_name_plural = "Sucursales"
        ordering = ["comercio__nombre_fantasia", "nombre"]
        constraints = [
            models.CheckConstraint(
                condition=Q(latitud__gte=-90) & Q(latitud__lte=90),
                name="chk_sucursal_latitud_valida",
            ),
            models.CheckConstraint(
                condition=Q(longitud__gte=-180) & Q(longitud__lte=180),
                name="chk_sucursal_longitud_valida",
            ),
        ]
        indexes = [
            models.Index(fields=["sector", "activa"]),
        ]

    def __str__(self) -> str:
        return f"{self.comercio.nombre_fantasia} — {self.nombre}"

    def save(self, *args, **kwargs):
        # Evaluar automáticamente si la coordenada cae fuera de Pedro Aguirre Cerda (# Sección 1.6)
        if getattr(settings, "VALIDAR_LIMITE_COMUNA", True) and self.latitud is not None and self.longitud is not None:
            from apps.comercios.geo import esta_en_comuna

            self.fuera_de_comuna = not esta_en_comuna(float(self.latitud), float(self.longitud))
        super().save(*args, **kwargs)

    @property
    def nombre_visible(self) -> str:
        if self.nombre.lower() in self.comercio.nombre_fantasia.lower():
            return self.comercio.nombre_fantasia
        return f"{self.comercio.nombre_fantasia} ({self.nombre})"


class UsoApiMapas(models.Model):
    """Contador diario de llamadas al proxy de mapas/geocodificación para controlar cuota (# Sección 2.3)."""

    fecha = models.DateField("Fecha", db_index=True)
    endpoint = models.CharField("Endpoint", max_length=40)
    cantidad = models.PositiveIntegerField("Cantidad de llamadas", default=0)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Uso diario API de mapas"
        verbose_name_plural = "Uso diario API de mapas"
        constraints = [
            models.UniqueConstraint(fields=["fecha", "endpoint"], name="unico_uso_api_mapas_fecha_endpoint"),
        ]
        ordering = ["-fecha", "endpoint"]

    def __str__(self) -> str:
        return f"{self.fecha} · {self.endpoint}: {self.cantidad}"
