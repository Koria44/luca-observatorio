"""
Endpoints GeoJSON propios para el mapa público con MapLibre GL JS (# REQ-05, ADR-005).

- `/api/mapa/config/`: configuración de la comuna (centroide, bbox, maxBounds, polígono
  `limite_comuna` y estilo Geoapify con `GEOAPIFY_KEY_NAVEGADOR` únicamente).
- `/api/mapa/sucursales/`: consulta PostGIS (`geo.en_vista` / `geo.cercanas`) y devuelve
  GeoJSON con caché corto y sin exponer jamás datos personales ni claves de servidor.
"""
from django.conf import settings
from django.http import JsonResponse

from apps.comercios import geo
from apps.comercios.models import Sucursal
from apps.precios.models import Precio


def _construir_url_estilo() -> str:
    """Arma la URL de estilo vectorial del proveedor configurado usando la clave de navegador."""
    proveedor = getattr(settings, "PROVEEDOR_MAPAS", "geoapify")
    clave_nav = getattr(settings, "GEOAPIFY_KEY_NAVEGADOR", "").strip()
    estilo = getattr(settings, "GEOAPIFY_ESTILO", "osm-bright")
    if proveedor == "geoapify" and clave_nav:
        return f"https://maps.geoapify.com/v1/styles/{estilo}/style.json?apiKey={clave_nav}"
    return ""


def api_mapa_config(request):
    """Entrega configuración geográfica de Pedro Aguirre Cerda y metadatos de atribución."""
    cfg = geo.obtener_config_comuna()
    estilo_url = _construir_url_estilo()
    resp = JsonResponse(
        {
            "proveedor": getattr(settings, "PROVEEDOR_MAPAS", "geoapify"),
            "estilo_url": estilo_url,
            "tiene_clave_mapa": bool(estilo_url),
            "atribucion": "Powered by Geoapify · © OpenMapTiles · © OpenStreetMap contributors",
            **cfg,
        }
    )
    if settings.DEBUG or not estilo_url:
        resp["Cache-Control"] = "no-store"
    else:
        resp["Cache-Control"] = "public, max-age=300"
    return resp


def api_mapa_sucursales(request):
    """
    Devuelve GeoJSON de sucursales activas filtradas por `bbox`, cercanía (`lat`/`lng`),
    `tipo`, `sector`, `categoria` o `producto`.
    # SEGURIDAD: Nunca incluye datos personales del propietario (solo datos comerciales públicos).
    """
    bbox_str = request.GET.get("bbox", "").strip()
    tipo = request.GET.get("tipo", "").strip()
    sector = request.GET.get("sector", "").strip()
    cat_slug = request.GET.get("categoria", "").strip()
    producto_id = request.GET.get("producto", "").strip()
    lat_str = request.GET.get("lat", "").strip()
    lng_str = request.GET.get("lng", "").strip()

    sucursales_qs = Sucursal.objects.filter(
        activa=True, verificada_mapa=True, comercio__activo=True, comercio__estado="ACTIVO"
    ).select_related("comercio")

    distancias = {}
    if lat_str and lng_str:
        try:
            cerc = geo.cercanas(float(lat_str), float(lng_str), radio_m=15000, limite=150)
            distancias = {c["id_sucursal"]: c["distancia_m"] for c in cerc}
            sucursales_qs = sucursales_qs.filter(id__in=list(distancias.keys()))
        except (TypeError, ValueError):
            pass
    elif bbox_str:
        try:
            oeste, sur, este, norte = [float(x) for x in bbox_str.split(",")]
            ids_vista = geo.en_vista(oeste, sur, este, norte, limite=150)
            sucursales_qs = sucursales_qs.filter(id__in=ids_vista)
        except (TypeError, ValueError):
            pass

    if tipo:
        sucursales_qs = sucursales_qs.filter(comercio__tipo=tipo)
    if sector:
        sucursales_qs = sucursales_qs.filter(sector=sector)
    if cat_slug:
        ids_cat = (
            Precio.objects.vigentes()
            .filter(producto__categoria__slug=cat_slug)
            .values_list("sucursal_id", flat=True)
            .distinct()
        )
        sucursales_qs = sucursales_qs.filter(id__in=ids_cat)

    # Si se filtró por un producto específico, adjuntamos el precio vigente y destacamos el más barato
    precios_prod = {}
    min_precio = None
    if producto_id.isdigit():
        for pr in Precio.objects.vigentes().filter(producto_id=int(producto_id)).select_related("producto"):
            val = pr.precio_vigente
            if pr.sucursal_id not in precios_prod or val < precios_prod[pr.sucursal_id]["precio"]:
                precios_prod[pr.sucursal_id] = {
                    "precio": val,
                    "fecha": pr.fecha_observacion.strftime("%d/%m/%Y"),
                    "condiciones": ", ".join(pr.etiquetas_condiciones),
                }
                if min_precio is None or val < min_precio:
                    min_precio = val
        sucursales_qs = sucursales_qs.filter(id__in=list(precios_prod.keys()))

    sucursales_lista = list(sucursales_qs[:150])
    if distancias:
        sucursales_lista.sort(key=lambda s: distancias.get(s.id, 999999))

    features = []
    for s in sucursales_lista:
        dist_m = distancias.get(s.id)
        info_p = precios_prod.get(s.id)
        features.append(
            {
                "type": "Feature",
                "geometry": {
                    "type": "Point",
                    "coordinates": [float(s.longitud), float(s.latitud)],
                },
                "properties": {
                    "id": s.id,
                    "nombre": s.nombre_visible,
                    "comercio": s.comercio.nombre_fantasia,
                    "tipo": s.comercio.tipo,
                    "tipo_texto": s.comercio.get_tipo_display(),
                    "direccion": s.direccion,
                    "sector": s.sector,
                    "horario": s.horario,
                    "telefono": s.telefono or s.comercio.telefono or "",
                    "url": f"/comercio/{s.id}/",
                    "logo_url": s.comercio.url_logo_publico,
                    "iniciales": s.comercio.iniciales_monograma,
                    "color_monograma": s.comercio.color_monograma,
                    "distancia_m": dist_m,
                    "distancia_texto": geo.formatear_distancia(dist_m),
                    "precio": info_p["precio"] if info_p else None,
                    "precio_fecha": info_p["fecha"] if info_p else "",
                    "precio_condiciones": info_p["condiciones"] if info_p else "",
                    "es_mas_barato": bool(info_p and min_precio is not None and info_p["precio"] == min_precio),
                },
            }
        )

    resp = JsonResponse({"type": "FeatureCollection", "features": features})
    resp["Cache-Control"] = "public, max-age=60"
    return resp
