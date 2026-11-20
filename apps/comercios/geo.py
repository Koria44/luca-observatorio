"""
Servicio geográfico unificado sobre PostGIS (PostgreSQL) con respaldo compatible para SQLite
en desarrollo local (# ADR-005 / REQ-02, REQ-04, REQ-05).

# SEGURIDAD: Todas las consultas SQL son estrictamente parametrizadas (nunca f-strings).
"""
import json
from functools import lru_cache
from pathlib import Path

from django.conf import settings
from django.db import connection

from apps.nucleo.validadores import distancia_haversine_km

LIMITE_PAC_PATH = Path(settings.BASE_DIR) / "data" / "limite_pac.geojson"

# Centroide y bbox referencial de Pedro Aguirre Cerda
CENTROIDE_PAC = {"lat": -33.4910, "lng": -70.6745}
BBOX_PAC = [-70.6950, -33.5090, -70.6580, -33.4740]  # [oeste, sur, este, norte]


@lru_cache(maxsize=1)
def cargar_geojson_comuna() -> dict:
    """Lee el polígono GeoJSON oficial/referencial de Pedro Aguirre Cerda."""
    return json.loads(LIMITE_PAC_PATH.read_text(encoding="utf-8"))


def _punto_en_anillo(lng: float, lat: float, anillo: list[list[float]]) -> bool:
    """Algoritmo ray-casting sobre un anillo de coordenadas [lng, lat] (respaldo SQLite)."""
    dentro = False
    n = len(anillo)
    j = n - 1
    for i in range(n):
        xi, yi = anillo[i][0], anillo[i][1]
        xj, yj = anillo[j][0], anillo[j][1]
        if ((yi > lat) != (yj > lat)) and (lng < (xj - xi) * (lat - yi) / ((yj - yi) or 1e-12) + xi):
            dentro = not dentro
        j = i
    return dentro


def _es_postgresql() -> bool:
    return connection.vendor == "postgresql"


def cercanas(lat: float, lng: float, radio_m: float = 3000.0, limite: int = 50) -> list[dict]:
    """
    Devuelve las sucursales activas dentro de `radio_m` metros ordenadas por distancia ascendente.
    En PostgreSQL invoca `luca_sucursales_cercanas(lat, lng, radio_m, limite)` con índice GIST.
    """
    lat_f, lng_f, radio_f, lim_i = float(lat), float(lng), float(radio_m), int(limite)
    if _es_postgresql():
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT id_sucursal, distancia_m FROM luca_sucursales_cercanas(%s, %s, %s, %s);",
                [lat_f, lng_f, radio_f, lim_i],
            )
            return [{"id_sucursal": r[0], "distancia_m": round(float(r[1]), 1)} for r in cursor.fetchall()]

    # Respaldo equivalente para SQLite local
    from apps.comercios.models import Sucursal

    resultados = []
    for suc in Sucursal.objects.filter(activa=True, comercio__activo=True, comercio__estado="ACTIVO").only("id", "latitud", "longitud"):
        dist_m = distancia_haversine_km(lat_f, lng_f, float(suc.latitud), float(suc.longitud)) * 1000.0
        if dist_m <= radio_f:
            resultados.append({"id_sucursal": suc.id, "distancia_m": round(dist_m, 1)})
    resultados.sort(key=lambda x: x["distancia_m"])
    return resultados[:lim_i]


def en_vista(oeste: float, sur: float, este: float, norte: float, limite: int = 200) -> list[int]:
    """
    Devuelve los IDs de sucursales activas dentro del recuadro visible (bbox) del mapa.
    En PostgreSQL invoca `luca_sucursales_en_vista(oeste, sur, este, norte)`.
    """
    o, s, e, n = float(oeste), float(sur), float(este), float(norte)
    if _es_postgresql():
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT id_sucursal FROM luca_sucursales_en_vista(%s, %s, %s, %s) LIMIT %s;",
                [o, s, e, n, int(limite)],
            )
            return [r[0] for r in cursor.fetchall()]

    from apps.comercios.models import Sucursal

    return list(
        Sucursal.objects.filter(
            activa=True,
            verificada_mapa=True,
            comercio__activo=True,
            comercio__estado="ACTIVO",
            longitud__gte=o,
            longitud__lte=e,
            latitud__gte=s,
            latitud__lte=n,
        ).values_list("id", flat=True)[: int(limite)]
    )


def esta_en_comuna(lat: float, lng: float) -> bool:
    """Indica si el punto `(lat, lng)` se encuentra dentro del límite de Pedro Aguirre Cerda."""
    lat_f, lng_f = float(lat), float(lng)
    if _es_postgresql():
        with connection.cursor() as cursor:
            cursor.execute("SELECT luca_punto_en_comuna(%s, %s);", [lat_f, lng_f])
            fila = cursor.fetchone()
            return bool(fila and fila[0])

    geojson = cargar_geojson_comuna()
    for feat in geojson.get("features", []):
        coords = feat.get("geometry", {}).get("coordinates", [])
        for poligono in coords:
            if poligono and _punto_en_anillo(lng_f, lat_f, poligono[0]):
                return True
    return False


def sector_de(lat: float, lng: float) -> str | None:
    """
    Devuelve el sector aproximado si existe capa oficial de unidades vecinales cargada.
    Actualmente se documenta como pendiente la capa poligonal oficial de unidades vecinales
    y el usuario selecciona el sector en el formulario (# Sección 1.2).
    """
    return None


def formatear_distancia(distancia_m: float | None) -> str:
    """Formatea una distancia en metros a texto humano chileno ('a 650 m' / 'a 1,3 km')."""
    if distancia_m is None:
        return ""
    if distancia_m < 1000:
        return f"a {int(round(distancia_m))} m"
    km = f"{distancia_m / 1000.0:.1f}".replace(".", ",")
    return f"a {km} km"


def obtener_config_comuna() -> dict:
    """Devuelve configuración geométrica de la comuna para inicializar MapLibre GL JS."""
    return {
        "nombre": "Pedro Aguirre Cerda",
        "centroide": CENTROIDE_PAC,
        "bbox": BBOX_PAC,
        "max_bounds": [
            [BBOX_PAC[0] - 0.025, BBOX_PAC[1] - 0.020],
            [BBOX_PAC[2] + 0.025, BBOX_PAC[3] + 0.020],
        ],
        "limite_geojson": cargar_geojson_comuna(),
    }
