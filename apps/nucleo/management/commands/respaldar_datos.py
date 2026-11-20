"""
Comando `python manage.py respaldar_datos` para generar respaldos lógicos portables (# REQ-16).

Genera un volcado JSON con timestamp de todas las apps de dominio (`cuentas`, `catalogo`,
`comercios`, `precios`, `auditoria`, `verificacion`) en `docs/evidencia/respaldo/` o la ruta
indicada, permitiendo pruebas reales de restauración sin depender de utilidades externas.
"""
from datetime import datetime
from pathlib import Path

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Genera un respaldo JSON completo de los datos de dominio de Luca (# REQ-16)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--salida",
            type=str,
            default="",
            help="Ruta del archivo de respaldo JSON. Si se omite, usa docs/evidencia/respaldo/.",
        )

    def handle(self, *args, **options):
        if options["salida"]:
            ruta = Path(options["salida"])
        else:
            carpeta = Path(settings.BASE_DIR) / "docs" / "evidencia" / "respaldo"
            carpeta.mkdir(parents=True, exist_ok=True)
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            ruta = carpeta / f"respaldo_luca_{ts}.json"

        ruta.parent.mkdir(parents=True, exist_ok=True)
        with ruta.open("w", encoding="utf-8") as f:
            call_command(
                "dumpdata",
                "cuentas",
                "catalogo",
                "comercios",
                "precios",
                "auditoria",
                "verificacion",
                indent=2,
                stdout=f,
            )
        tam_kb = round(ruta.stat().st_size / 1024, 1)
        self.stdout.write(self.style.SUCCESS(f"Respaldo generado correctamente: {ruta} ({tam_kb} KB)"))
