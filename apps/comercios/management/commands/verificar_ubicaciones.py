"""
Comando `python manage.py verificar_ubicaciones [--aplicar] [--limite 400]` (# Prompt 5 Sección 2.5).

Compara las coordenadas actuales de las sucursales contra Geoapify (clave servidor),
respetando <= 5 solicitudes/segundo y el tope diario `GEO_TOPE_DIARIO_PROXY`, y genera
`docs/evidencia/geolocalizacion/verificacion.csv`. Por defecto corre en modo simulación.
"""
import csv
import time
from decimal import Decimal
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

from apps.comercios.geo_proxy import _consumir_cuota_diaria, _llamar_geoapify, _normalizar_sugerencias
from apps.comercios.models import Sucursal
from apps.nucleo.validadores import distancia_haversine_km


class Command(BaseCommand):
    help = "Compara ubicaciones de sucursales contra Geoapify y genera informe CSV (simulación por defecto)."

    def add_arguments(self, parser):
        parser.add_argument("--aplicar", action="store_true", help="Actualiza sucursales no verificadas con diferencia > 150 m.")
        parser.add_argument("--limite", type=int, default=400, help="Máximo de sucursales a consultar.")

    def handle(self, *args, **options):
        aplicar = options["aplicar"]
        limite = min(options["limite"], 400)
        clave = getattr(settings, "GEOAPIFY_KEY_SERVIDOR", "").strip()

        out_dir = Path(settings.BASE_DIR) / "docs" / "evidencia" / "geolocalizacion"
        out_dir.mkdir(parents=True, exist_ok=True)
        ruta_csv = out_dir / "verificacion.csv"

        sucursales = list(Sucursal.objects.select_related("comercio").all()[:limite])
        actualizadas = 0

        with ruta_csv.open("w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f)
            writer.writerow(["sucursal_id", "nombre", "direccion", "lat_actual", "lng_actual", "lat_geo", "lng_geo", "diferencia_m", "estado"])

            for suc in sucursales:
                if not clave:
                    writer.writerow([suc.id, suc.nombre_visible, suc.direccion, suc.latitud, suc.longitud, "", "", "", "SIN_CLAVE_SERVIDOR"])
                    continue
                if not _consumir_cuota_diaria("verificar_ubicaciones"):
                    writer.writerow([suc.id, suc.nombre_visible, suc.direccion, suc.latitud, suc.longitud, "", "", "", "TOPE_DIARIO_ALCANZADO"])
                    break

                status_code, payload = _llamar_geoapify("search", {"text": suc.direccion, "lang": "es", "limit": 1, "filter": "countrycode:cl"})
                time.sleep(0.22)  # <= 5 solicitudes/segundo
                if status_code != 200 or not payload:
                    writer.writerow([suc.id, suc.nombre_visible, suc.direccion, suc.latitud, suc.longitud, "", "", "", f"ERROR_{status_code}"])
                    continue

                res = _normalizar_sugerencias(payload)
                if not res:
                    writer.writerow([suc.id, suc.nombre_visible, suc.direccion, suc.latitud, suc.longitud, "", "", "", "SIN_RESULTADO"])
                    continue

                geo_lat, geo_lng = res[0]["lat"], res[0]["lng"]
                diff_m = round(distancia_haversine_km(float(suc.latitud), float(suc.longitud), geo_lat, geo_lng) * 1000.0, 1)
                estado = "OK"
                if diff_m > 150 and not suc.ubicacion_verificada:
                    estado = "DIFIERE_>150M"
                    if aplicar:
                        suc.latitud = Decimal(f"{geo_lat:.6f}")
                        suc.longitud = Decimal(f"{geo_lng:.6f}")
                        suc.origen_coordenada = Sucursal.OrigenCoordenada.GEOAPIFY
                        suc.save()
                        actualizadas += 1
                        estado = "ACTUALIZADA"
                writer.writerow([suc.id, suc.nombre_visible, suc.direccion, suc.latitud, suc.longitud, geo_lat, geo_lng, diff_m, estado])

        self.stdout.write(self.style.SUCCESS(f"Verificación finalizada ({'APLICADO' if aplicar else 'SIMULACIÓN'}). Actualizadas: {actualizadas}. Informe: {ruta_csv}"))
