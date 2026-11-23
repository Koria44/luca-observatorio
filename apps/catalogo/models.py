"""
Modelos del catálogo maestro de productos de Luca (# REQ-01).

Normaliza categorías, marcas, formatos, contenido y unidad de medida (`contenido_base`)
para poder comparar precios por kilo, litro o unidad sin resultados engañosos.
"""
from decimal import Decimal

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils.text import slugify


class Categoria(models.Model):
    """Categoría normalizada de productos (ej. Abarrotes, Lácteos, Farmacia)."""

    nombre = models.CharField("Nombre", max_length=80, unique=True)
    slug = models.SlugField("Slug", max_length=90, unique=True)
    icono = models.CharField("Ícono", max_length=30, default="🛒")
    color = models.CharField("Color hexadecimal", max_length=16, default="#0F8B8D")
    orden = models.PositiveSmallIntegerField("Orden de visualización", default=0)
    activa = models.BooleanField("Activa", default=True)
    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Categoría"
        verbose_name_plural = "Categorías"
        ordering = ["orden", "nombre"]

    def __str__(self) -> str:
        return self.nombre

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.nombre)
        super().save(*args, **kwargs)


class Marca(models.Model):
    """Marca comercial normalizada para evitar duplicados de escritura."""

    nombre = models.CharField("Nombre", max_length=100, unique=True)
    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Marca"
        verbose_name_plural = "Marcas"
        ordering = ["nombre"]

    def __str__(self) -> str:
        return self.nombre


class ProductoGenerico(models.Model):
    """
    Ficha canónica sin marca (# Prompt 7 Sección 6).
    Agrupa productos equivalentes (misma unidad base dentro de la tolerancia de contenido)
    para comparar 'cualquier marca' y calcular indicadores de canasta básica estables.
    """

    class UnidadBase(models.TextChoices):
        GRAMO = "g", "Gramos (g)"
        MILILITRO = "ml", "Mililitros (ml)"
        UNIDAD = "un", "Unidades (un)"

    nombre = models.CharField("Nombre canónico genérico", max_length=150, unique=True, db_index=True)
    categoria = models.ForeignKey(Categoria, on_delete=models.PROTECT, related_name="genericos")
    subcategoria = models.CharField("Subcategoría", max_length=100, blank=True)
    unidad_base = models.CharField("Unidad base", max_length=5, choices=UnidadBase.choices, default=UnidadBase.GRAMO)
    contenido_base = models.DecimalField("Contenido base referencial (g/ml/un)", max_digits=12, decimal_places=2, default=Decimal("1000"))
    tolerancia_pct = models.PositiveSmallIntegerField("Tolerancia de equivalencia (%)", default=5)
    es_canasta_basica = models.BooleanField("Parte de la canasta básica", default=False, db_index=True)
    es_a_granel = models.BooleanField("Producto a granel / sin marca", default=False)
    descripcion = models.TextField("Descripción simple", blank=True)
    activo = models.BooleanField(default=True, db_index=True)
    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Producto genérico"
        verbose_name_plural = "Productos genéricos"
        ordering = ["categoria__orden", "nombre"]

    def __str__(self) -> str:
        return self.nombre

    def productos_equivalentes(self):
        """Devuelve productos activos de este genérico dentro de la tolerancia de contenido (# Sección 6.2)."""
        factor = Decimal(self.tolerancia_pct) / Decimal("100")
        minimo = self.contenido_base * (Decimal("1") - factor)
        maximo = self.contenido_base * (Decimal("1") + factor)
        unidades_compat = {
            "g": ["g", "kg"],
            "ml": ["ml", "l"],
            "un": ["un"],
        }.get(self.unidad_base, ["un"])
        return self.productos.filter(
            activo=True,
            descontinuado=False,
            unidad_medida__in=unidades_compat,
            contenido_base__gte=minimo,
            contenido_base__lte=maximo,
        ).select_related("marca", "categoria")


class Producto(models.Model):
    """
    Producto del catálogo maestro (# REQ-01).
    La restricción única `(nombre, marca, contenido, unidad_medida)` impide duplicados
    y distingue explícitamente formatos distintos (ej. arroz 1 kg vs. 500 g).
    """

    class UnidadMedida(models.TextChoices):
        GRAMO = "g", "g"
        KILOGRAMO = "kg", "kg"
        MILILITRO = "ml", "ml"
        LITRO = "l", "L"
        UNIDAD = "un", "un"

    codigo_barras = models.CharField(
        "Código de barras (EAN)", max_length=32, unique=True, null=True, blank=True
    )
    nombre = models.CharField("Nombre del producto", max_length=150, db_index=True)
    categoria = models.ForeignKey(
        Categoria, on_delete=models.PROTECT, related_name="productos", verbose_name="Categoría"
    )
    marca = models.ForeignKey(
        Marca, on_delete=models.PROTECT, related_name="productos", verbose_name="Marca"
    )
    formato = models.CharField("Formato / envase", max_length=60, default="envase")
    contenido = models.DecimalField("Contenido", max_digits=10, decimal_places=2)
    unidad_medida = models.CharField(
        "Unidad de medida", max_length=5, choices=UnidadMedida.choices
    )
    # Contenido normalizado a unidad base (gramos, mililitros o unidades)
    contenido_base = models.DecimalField(
        "Contenido en unidad base (g/ml/un)", max_digits=12, decimal_places=2, editable=False, default=Decimal("1")
    )
    class TipoMarca(models.TextChoices):
        MARCA = "MARCA", "Marca comercial"
        MARCA_PROPIA = "MARCA_PROPIA", "Marca propia de comercio"
        GENERICO_SIN_MARCA = "GENERICO_SIN_MARCA", "Genérico / sin marca (a granel)"

    class EstadoBioequivalencia(models.TextChoices):
        NO_APLICA = "NO_APLICA", "No aplica"
        NO_VERIFICADO = "NO_VERIFICADO", "No verificado contra ISP"
        CERTIFICADO_ISP = "CERTIFICADO_ISP", "Bioequivalente certificado (ISP)"

    es_canasta_basica = models.BooleanField("Parte de la canasta básica", default=False, db_index=True)
    es_estrella = models.BooleanField("Producto estrella", default=False, db_index=True)
    activo = models.BooleanField("Activo", default=True, db_index=True)
    descontinuado = models.BooleanField("Descontinuado (conserva historial)", default=False, db_index=True)
    generico = models.ForeignKey(
        ProductoGenerico,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="productos",
        verbose_name="Producto genérico canónico",
    )
    tipo_marca = models.CharField("Tipo de marca", max_length=25, choices=TipoMarca.choices, default=TipoMarca.MARCA)
    marca_propia_de = models.ForeignKey(
        "comercios.Comercio",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="productos_marca_propia",
        verbose_name="Marca propia de",
    )
    # Medicamentos de venta directa — tratamiento prudente (# Sección 6.5)
    es_medicamento_venta_directa = models.BooleanField("Medicamento de venta directa (sin receta)", default=False)
    principio_activo = models.CharField("Principio activo", max_length=120, blank=True)
    concentracion = models.CharField("Concentración", max_length=60, blank=True)
    forma_farmaceutica = models.CharField("Forma farmacéutica", max_length=60, blank=True)
    es_bioequivalente_certificado = models.CharField(
        "Bioequivalencia ISP",
        max_length=20,
        choices=EstadoBioequivalencia.choices,
        default=EstadoBioequivalencia.NO_APLICA,
    )
    fecha_consulta_isp = models.DateField("Fecha de verificación ISP", null=True, blank=True)
    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Producto"
        verbose_name_plural = "Productos"
        ordering = ["nombre", "marca__nombre", "contenido"]
        constraints = [
            models.UniqueConstraint(
                fields=["nombre", "marca", "contenido", "unidad_medida"],
                name="unico_producto_marca_formato",
            ),
            models.CheckConstraint(
                condition=models.Q(contenido__gt=0),
                name="chk_producto_contenido_positivo",
            ),
        ]
        indexes = [
            models.Index(fields=["categoria", "activo"]),
            models.Index(fields=["nombre", "activo"]),
        ]

    def __str__(self) -> str:
        return self.nombre_completo

    def save(self, *args, **kwargs):
        # Normaliza contenido_base a gramos, mililitros o unidades (# REQ-01 / REQ-04)
        factor = Decimal("1000") if self.unidad_medida in ("kg", "l") else Decimal("1")
        self.contenido_base = (Decimal(str(self.contenido)) * factor).quantize(Decimal("0.01"))
        super().save(*args, **kwargs)

    @property
    def contenido_legible(self) -> str:
        val = Decimal(str(self.contenido)).normalize()
        # Evitar notación científica en decimales enteros como 1E+2
        texto = format(val, "f").rstrip("0").rstrip(".") if "." in format(val, "f") else format(val, "f")
        return f"{texto} {self.get_unidad_medida_display()}"

    @property
    def nombre_completo(self) -> str:
        return f"{self.nombre} {self.marca.nombre} {self.contenido_legible}"

    @property
    def etiqueta_unidad_comparacion(self) -> str:
        """Etiqueta de la unidad usada para comparar formatos equivalentes."""
        if self.unidad_medida in ("g", "kg"):
            return "kg"
        if self.unidad_medida in ("ml", "l"):
            return "L"
        return "un"

    @property
    def imagen_por_defecto(self) -> dict:
        """
        Resuelve la imagen a mostrar según la prioridad oficial (# Prompt 5 Sección 3.1):
        1. Imagen marcada `es_principal=True` y `estado=APROBADA`.
        2. Imagen `APROBADA` más reciente subida por fiscalizador/admin.
        3. Imagen `APROBADA` más reciente subida por un comercio.
        4. Placeholder SVG propio por categoría de Luca.
        """
        aprobadas = list(self.imagenes.filter(estado=ImagenProducto.Estado.APROBADA).order_by("-creado_en"))
        elegida = next((i for i in aprobadas if i.es_principal), None)
        if not elegida:
            elegida = next((i for i in aprobadas if i.rol_origen in ("FISCALIZADOR", "ADMIN")), None)
        if not elegida and aprobadas:
            elegida = aprobadas[0]

        if elegida:
            return {
                "es_placeholder": False,
                "url_miniatura": elegida.url_miniatura,
                "url_media": elegida.url_media,
                "url_grande": elegida.url_grande,
                "alt": elegida.texto_alternativo or f"Foto de {self.nombre_completo}",
                "origen": elegida.get_rol_origen_display(),
                "atribucion": elegida.atribucion,
                "licencia": elegida.licencia,
                "fuente_url": elegida.fuente_url,
            }

        slug = self.categoria.slug if self.categoria_id else "abarrotes"
        url_svg = f"/static/img/categorias/{slug}.svg"
        return {
            "es_placeholder": True,
            "url_miniatura": url_svg,
            "url_media": url_svg,
            "url_grande": url_svg,
            "alt": f"Ilustración referencial de {self.nombre_completo}",
            "origen": "Ilustración Luca",
            "atribucion": "",
            "licencia": "",
            "fuente_url": "",
        }


class ImagenProducto(models.Model):
    """
    Fotografía de un producto subida por comercio, fiscalizador, admin o semilla abierta
    (# REQ-01, REQ-12, REQ-13 / Prompt 5 Sección 3.1).
    """

    class RolOrigen(models.TextChoices):
        COMERCIANTE = "COMERCIANTE", "Comercio local"
        FISCALIZADOR = "FISCALIZADOR", "Fiscalizador municipal"
        ADMIN = "ADMIN", "Administrador DIDESE"
        DEMO_ABIERTA = "DEMO_ABIERTA", "Fuente abierta (demostración)"

    class Estado(models.TextChoices):
        PENDIENTE = "PENDIENTE", "En revisión"
        APROBADA = "APROBADA", "Aprobada"
        RECHAZADA = "RECHAZADA", "Rechazada"
        RETIRADA = "RETIRADA", "Retirada"

    producto = models.ForeignKey(Producto, on_delete=models.CASCADE, related_name="imagenes", verbose_name="Producto")
    comercio = models.ForeignKey(
        "comercios.Comercio",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="imagenes_productos",
        verbose_name="Comercio",
    )
    subida_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="imagenes_subidas",
        verbose_name="Subida por",
    )
    rol_origen = models.CharField("Origen", max_length=20, choices=RolOrigen.choices, default=RolOrigen.COMERCIANTE)

    # Rutas procesadas WebP (200 / 480 / 960 px)
    archivo_miniatura = models.CharField("Miniatura 200px", max_length=255)
    archivo_media = models.CharField("Media 480px", max_length=255)
    archivo_grande = models.CharField("Grande 960px", max_length=255)
    ancho = models.PositiveIntegerField("Ancho (px)", default=0)
    alto = models.PositiveIntegerField("Alto (px)", default=0)
    tamano_bytes = models.PositiveIntegerField("Tamaño (bytes)", default=0)

    texto_alternativo = models.CharField("Texto alternativo (accesibilidad)", max_length=200)
    estado = models.CharField("Estado", max_length=15, choices=Estado.choices, default=Estado.PENDIENTE, db_index=True)
    motivo_rechazo = models.TextField("Motivo de rechazo", blank=True)
    revisada_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="imagenes_revisadas",
        verbose_name="Revisada por",
    )
    fecha_revision = models.DateTimeField("Fecha de revisión", null=True, blank=True)
    es_principal = models.BooleanField("Imagen principal por defecto", default=False, db_index=True)
    declaracion_derechos = models.BooleanField("Declaración de derechos de uso", default=False)
    licencia = models.CharField("Licencia", max_length=120, blank=True)
    atribucion = models.CharField("Atribución", max_length=255, blank=True)
    fuente_url = models.URLField("URL de origen", blank=True)
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Imagen de producto"
        verbose_name_plural = "Imágenes de productos"
        ordering = ["-es_principal", "-creado_en"]
        constraints = [
            models.UniqueConstraint(
                fields=["producto"],
                condition=Q(es_principal=True),
                name="unica_imagen_principal_por_producto",
            ),
            models.CheckConstraint(
                condition=Q(es_principal=False) | Q(estado="APROBADA"),
                name="chk_solo_aprobada_es_principal",
            ),
        ]

    def __str__(self) -> str:
        return f"Imagen #{self.id} de {self.producto.nombre_completo} ({self.estado})"

    @property
    def url_miniatura(self) -> str:
        from apps.nucleo.imagenes import url_publica_imagen

        return url_publica_imagen(self.archivo_miniatura) if self.estado == self.Estado.APROBADA else ""

    @property
    def url_media(self) -> str:
        from apps.nucleo.imagenes import url_publica_imagen

        return url_publica_imagen(self.archivo_media) if self.estado == self.Estado.APROBADA else ""

    @property
    def url_grande(self) -> str:
        from apps.nucleo.imagenes import url_publica_imagen

        return url_publica_imagen(self.archivo_grande) if self.estado == self.Estado.APROBADA else ""


class ReporteImagen(models.Model):
    """Aviso ciudadano para reportar una imagen inapropiada o incorrecta (# Sección 3.3)."""

    imagen = models.ForeignKey(ImagenProducto, on_delete=models.CASCADE, related_name="reportes")
    motivo = models.CharField("Motivo del reporte", max_length=220)
    reportado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True
    )
    atendido = models.BooleanField("Atendido", default=False)
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Reporte de imagen"
        verbose_name_plural = "Reportes de imágenes"
        ordering = ["-creado_en"]
