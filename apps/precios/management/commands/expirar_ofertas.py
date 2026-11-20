"""Comando `python manage.py expirar_ofertas` para marcar ofertas vencidas (# REQ-09)."""
from django.core.management.base import BaseCommand

from apps.precios.servicios import expirar_ofertas_vencidas


class Command(BaseCommand):
    help = "Marca como VENCIDO los precios/ofertas publicados cuya fecha de vigencia ya expiró."

    def handle(self, *args, **options):
        n = expirar_ofertas_vencidas()
        self.stdout.write(self.style.SUCCESS(f"Ofertas vencidas actualizadas: {n}"))
