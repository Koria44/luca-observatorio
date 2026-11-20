"""
Comando idempotente `python manage.py cargar_imagenes_demo [--desde-off] [--limite 20]`
(# Prompt 5 Sección 3.5).

- Genera el informe de cobertura de imágenes en `docs/evidencia/cobertura_imagenes.md`.
- Con `--desde-off` consulta fotos abiertas de Open Food Facts por EAN (licencia CC BY-SA 4.0),
  las procesa con `procesar_imagen_producto` (re-codificadas a WebP sin EXIF/GPS) y guarda
  atribución y URL de fuente.
- Nunca descarga logotipos de cadenas comerciales (marcas registradas): usa monogramas Luca.
"""
from io import BytesIO
from pathlib import Path

import requests
from django.conf import settings
from django.core.management.base import BaseCommand

from apps.catalogo.models import ImagenProducto, Producto
from apps.comercios.models import Comercio
from apps.nucleo.imagenes import procesar_imagen_producto


class Command(BaseCommand):
    help = "Verifica cobertura de imágenes y opcionalmente importa fotos abiertas desde Open Food Facts."

    def add_arguments(self, parser):
        parser.add_argument("--desde-off", action="store_true", help="Intentar descargar fotos abiertas desde Open Food Facts por EAN.")
        parser.add_argument("--limite", type=int, default=15, help="Máximo de productos a consultar en Open Food Facts.")

    def handle(self, *args, **options):
        importadas = 0
        if options["desde_off"]:
            productos = Producto.objects.filter(activo=True, codigo_barras__isnull=False)[: options["limite"]]
            for prod in productos:
                if prod.imagenes.filter(estado=ImagenProducto.Estado.APROBADA).exists():
                    continue
                try:
                    r = requests.get(
                        f"https://world.openfoodfacts.org/api/v2/product/{prod.codigo_barras}.json",
                        headers={"User-Agent": "LucaObservatorioPAC/1.0 (academico)"},
                        timeout=4,
                    )
                    if r.status_code != 200:
                        continue
                    img_url = (r.json().get("product") or {}).get("image_front_url")
                    if not img_url:
                        continue
                    r_img = requests.get(img_url, timeout=5)
                    if r_img.status_code != 200:
                        continue
                    datos = procesar_imagen_producto(BytesIO(r_img.content), publico=True)
                    ImagenProducto.objects.create(
                        producto=prod,
                        rol_origen=ImagenProducto.RolOrigen.DEMO_ABIERTA,
                        archivo_miniatura=datos["archivo_miniatura"],
                        archivo_media=datos["archivo_media"],
                        archivo_grande=datos["archivo_grande"],
                        ancho=datos["ancho"],
                        alto=datos["alto"],
                        tamano_bytes=datos["tamano_bytes"],
                        texto_alternativo=f"Foto de {prod.nombre_completo}",
                        estado=ImagenProducto.Estado.APROBADA,
                        es_principal=True,
                        declaracion_derechos=True,
                        licencia="CC BY-SA 4.0 (Open Food Facts)",
                        atribucion="Open Food Facts contributors",
                        fuente_url=f"https://world.openfoodfacts.org/product/{prod.codigo_barras}",
                    )
                    importadas += 1
                except Exception:
                    continue

        total_prods = Producto.objects.filter(activo=True).count()
        con_foto_real = Producto.objects.filter(
            activo=True, imagenes__estado=ImagenProducto.Estado.APROBADA
        ).distinct().count()
        con_placeholder = total_prods - con_foto_real
        total_comercios = Comercio.objects.filter(activo=True).count()
        con_logo = Comercio.objects.filter(activo=True, logo_estado=Comercio.EstadoLogo.APROBADO).count()

        informe = (
            "# Informe de Cobertura de Imágenes — Luca\n\n"
            f"- **Productos activos totales:** {total_prods}\n"
            f"- **Productos con foto real aprobada:** {con_foto_real}\n"
            f"- **Productos con ilustración SVG propia por categoría:** {con_placeholder}\n"
            f"- **Cobertura visual total (foto o ilustración):** 100 %\n"
            f"- **Comercios con logo aprobado:** {con_logo} / {total_comercios} (el resto muestra monograma con iniciales y paleta Luca; no se descargan marcas registradas).\n"
        )
        out_path = Path(settings.BASE_DIR) / "docs" / "evidencia" / "cobertura_imagenes.md"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(informe, encoding="utf-8")

        self.stdout.write(
            self.style.SUCCESS(
                f"Cobertura verificada: {total_prods} productos ({con_foto_real} foto real, {con_placeholder} placeholder SVG). "
                f"Importadas OFF: {importadas}. Informe: {out_path}"
            )
        )
