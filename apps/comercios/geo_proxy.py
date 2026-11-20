"""
Proxy de geocodificación y autocompletado de direcciones sobre Geoapify (# REQ-02 / ADR-005).

# SEGURIDAD:
- Utiliza exclusivamente `GEOAPIFY_KEY_SERVIDOR` (secreta; jamás se expone al cliente ni en logs).
- Límite por IP (30 req/min en consultas públicas) y tope diario global (`GEO_TOPE_DIARIO_PROXY`)
  almacenado en `UsoApiMapas`.
- Caché persistente de 24 horas para consultas repetidas sin guardar datos personales.
- Timeout de 3 segundos y manejo elegante de errores 401/402/429 del proveedor.
"""
import hashlib
import re
import time
from collections import defaultdict

import requests
from django.conf import settings
from django.core.cache import cache
from django.db.models import F, Sum
from django.http import JsonResponse
from django.utils import timezone

from apps.comercios.geo import CENTROIDE_PAC
from apps.comercios.models import UsoApiMapas
from apps.nucleo.middleware import obtener_ip_cliente

_IP_GEO_HISTORIAL: dict[str, list[float]] = defaultdict(list)
CACHE_TTL_SEG = 86400  # 24 horas


def _sanear_consulta(texto: str) -> str:
    limpio = re.sub(r"[\x00-\x1f<>\"';]", " ", str(texto or "")).strip()
    return re.sub(r"\s+", " ", limpio)[:100]


def _supero_rate_limit_ip(request, max_por_minuto: int = 30) -> bool:
    if not getattr(settings, "RATELIMIT_ACTIVO", True):
        return False
    ip = obtener_ip_cliente(request)
    ahora = time.time()
    marcas = [t for t in _IP_GEO_HISTORIAL[ip] if ahora - t < 60]
    if len(marcas) >= max_por_minuto:
        _IP_GEO_HISTORIAL[ip] = marcas
        return True
    marcas.append(ahora)
    _IP_GEO_HISTORIAL[ip] = marcas
    return False


def obtener_consumo_diario_mapas() -> dict:
    """Devuelve el consumo acumulado de hoy vs. el tope configurado para el dashboard admin."""
    hoy = timezone.localdate()
    tope = getattr(settings, "GEO_TOPE_DIARIO_PROXY", 1500)
    usado = UsoApiMapas.objects.filter(fecha=hoy).aggregate(total=Sum("cantidad"))["total"] or 0
    return {"fecha": hoy, "usado": usado, "tope": tope, "porcentaje": min(100, round((usado / max(1, tope)) * 100))}


def _consumir_cuota_diaria(endpoint: str) -> bool:
    """Incrementa el contador diario en `UsoApiMapas`. Devuelve False si ya alcanzó el tope."""
    hoy = timezone.localdate()
    tope = getattr(settings, "GEO_TOPE_DIARIO_PROXY", 1500)
    usado_hoy = UsoApiMapas.objects.filter(fecha=hoy).aggregate(total=Sum("cantidad"))["total"] or 0
    if usado_hoy >= tope:
        return False
    obj, creado = UsoApiMapas.objects.get_or_create(fecha=hoy, endpoint=endpoint, defaults={"cantidad": 1})
    if not creado:
        UsoApiMapas.objects.filter(pk=obj.pk).update(cantidad=F("cantidad") + 1)
    return True


def _llamar_geoapify(ruta: str, params: dict) -> tuple[int, dict | None]:
    """Ejecuta la petición HTTP a Geoapify con timeout de 3 s sin registrar jamás la API key."""
    clave = getattr(settings, "GEOAPIFY_KEY_SERVIDOR", "").strip()
    if not clave:
        return 503, None
    url = f"https://api.geoapify.com/v1/geocode/{ruta}"
    parametros = {**params, "apiKey": clave}
    try:
        resp = requests.get(url, params=parametros, timeout=3.0)
        if resp.status_code == 200:
            return 200, resp.json()
        return resp.status_code, None
    except requests.RequestException:
        return 504, None


def _normalizar_sugerencias(payload: dict) -> list[dict]:
    """Extrae únicamente los campos útiles y seguros para el cliente."""
    sugerencias = []
    for feat in (payload or {}).get("features", [])[:5]:
        props = feat.get("properties") or {}
        coords = (feat.get("geometry") or {}).get("coordinates") or []
        if len(coords) < 2:
            continue
        rank = props.get("rank") or {}
        confianza = float(rank.get("confidence", 0.5))
        tipo_res = props.get("result_type", "unknown")
        sugerencias.append(
            {
                "direccion": props.get("formatted") or props.get("address_line1") or "",
                "calle": props.get("street") or "",
                "numero": props.get("housenumber") or "",
                "comuna": props.get("city") or props.get("suburb") or props.get("county") or "",
                "lat": round(float(coords[1]), 6),
                "lng": round(float(coords[0]), 6),
                "tipo_resultado": tipo_res,
                "confianza": round(confianza, 2),
                "requiere_ajuste": confianza < 0.7 or tipo_res in ("street", "suburb", "city", "unknown"),
            }
        )
    return sugerencias


def api_geo_autocompletar(request):
    """Autocompletado de direcciones en Chile sesgado a Pedro Aguirre Cerda."""
    if _supero_rate_limit_ip(request, max_por_minuto=30):
        return JsonResponse(
            {"error": "Demasiadas consultas seguidas. Espera un momento o ubica el pin en el mapa."},
            status=429,
        )

    q = _sanear_consulta(request.GET.get("q", ""))
    if len(q) < 3:
        return JsonResponse({"error": "Escribe al menos 3 caracteres para buscar una dirección."}, status=400)

    clave_cache = "geo_auto_" + hashlib.sha256(q.lower().encode("utf-8")).hexdigest()[:24]
    en_cache = cache.get(clave_cache)
    if en_cache is not None:
        return JsonResponse({"resultados": en_cache, "cache": True})

    if not _consumir_cuota_diaria("autocompletar"):
        return JsonResponse(
            {"error": "La búsqueda de direcciones no está disponible por hoy; ubique el pin en el mapa."},
            status=429,
        )

    status_code, payload = _llamar_geoapify(
        "autocomplete",
        {
            "text": q,
            "lang": "es",
            "limit": 5,
            "filter": "countrycode:cl",
            "bias": f"proximity:{CENTROIDE_PAC['lng']},{CENTROIDE_PAC['lat']}",
        },
    )
    if status_code != 200 or payload is None:
        return JsonResponse(
            {"resultados": [], "aviso": "Búsqueda temporalmente no disponible; ubique el pin manualmente en el mapa."},
            status=200 if status_code in (401, 402, 429, 503, 504) else 502,
        )

    resultados = _normalizar_sugerencias(payload)
    cache.set(clave_cache, resultados, CACHE_TTL_SEG)
    return JsonResponse({"resultados": resultados, "cache": False})


def api_geo_buscar(request):
    """Geocodificación directa de una dirección escrita."""
    if _supero_rate_limit_ip(request, max_por_minuto=30):
        return JsonResponse({"error": "Demasiadas solicitudes. Intenta en un minuto."}, status=429)

    q = _sanear_consulta(request.GET.get("q", ""))
    if len(q) < 3:
        return JsonResponse({"error": "Ingresa al menos 3 caracteres."}, status=400)

    clave_cache = "geo_busq_" + hashlib.sha256(q.lower().encode("utf-8")).hexdigest()[:24]
    en_cache = cache.get(clave_cache)
    if en_cache is not None:
        return JsonResponse({"resultados": en_cache, "cache": True})

    if not _consumir_cuota_diaria("buscar"):
        return JsonResponse(
            {"error": "La búsqueda de direcciones no está disponible por hoy; ubique el pin en el mapa."},
            status=429,
        )

    status_code, payload = _llamar_geoapify(
        "search",
        {
            "text": q,
            "lang": "es",
            "limit": 5,
            "filter": "countrycode:cl",
            "bias": f"proximity:{CENTROIDE_PAC['lng']},{CENTROIDE_PAC['lat']}",
        },
    )
    if status_code != 200 or payload is None:
        return JsonResponse({"resultados": [], "aviso": "No se pudo consultar el servicio de direcciones."})

    resultados = _normalizar_sugerencias(payload)
    cache.set(clave_cache, resultados, CACHE_TTL_SEG)
    return JsonResponse({"resultados": resultados, "cache": False})


def api_geo_inversa(request):
    """Geocodificación inversa para sugerir dirección al soltar el pin arrastrable."""
    if not request.user.is_authenticated:
        return JsonResponse({"error": "Debes iniciar sesión para usar la geocodificación inversa."}, status=403)
    if _supero_rate_limit_ip(request, max_por_minuto=30):
        return JsonResponse({"error": "Demasiadas solicitudes. Espera un momento."}, status=429)

    try:
        lat = round(float(request.GET.get("lat", "")), 5)
        lon = round(float(request.GET.get("lon", "")), 5)
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            raise ValueError()
    except (TypeError, ValueError):
        return JsonResponse({"error": "Coordenadas inválidas."}, status=400)

    clave_cache = f"geo_inv_{lat}_{lon}"
    en_cache = cache.get(clave_cache)
    if en_cache is not None:
        return JsonResponse({"resultado": en_cache, "cache": True})

    if not _consumir_cuota_diaria("inversa"):
        return JsonResponse(
            {"error": "La búsqueda de direcciones no está disponible por hoy; escribe la dirección manualmente."},
            status=429,
        )

    status_code, payload = _llamar_geoapify("reverse", {"lat": lat, "lon": lon, "lang": "es", "limit": 1})
    if status_code != 200 or payload is None:
        return JsonResponse({"resultado": None, "aviso": "No fue posible sugerir una dirección automática."})

    lista = _normalizar_sugerencias(payload)
    resultado = lista[0] if lista else None
    cache.set(clave_cache, resultado, CACHE_TTL_SEG)
    return JsonResponse({"resultado": resultado, "cache": False})
