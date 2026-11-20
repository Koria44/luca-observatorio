"""
Vistas públicas del portal ciudadano de Luca (# REQ-04, REQ-05, REQ-06, REQ-11, REQ-12, REQ-13).

El portal ciudadano es 100 % abierto y gratuito para cualquier vecino sin iniciar sesión.
"""
import json
from collections import defaultdict

from django.db.models import Avg, Count, Min
from django.shortcuts import get_object_or_404, render
from django.utils import timezone

from apps.catalogo.models import Categoria, Producto
from apps.comercios.models import Comercio, Sucursal
from apps.nucleo.validadores import SECTORES_PAC
from apps.precios.models import Banner, Precio

from .busqueda import coincide_producto
from .ferias import obtener_ferias_por_dia


def vista_inicio(request):
    """Portada ciudadana: buscador gigante, categorías, carrusel, 'Hoy conviene', KPIs y mapa mini."""
    categorias = Categoria.objects.filter(activa=True).order_by("orden")
    banners = Banner.objects.filter(activo=True).order_by("orden")[:6]

    ofertas_top = list(
        Precio.objects.ofertas_vigentes()
        .select_related("producto", "producto__marca", "producto__categoria", "sucursal", "sucursal__comercio")
        .order_by("-fecha_observacion")[:24]
    )
    ofertas_top.sort(key=lambda p: p.porcentaje_descuento, reverse=True)
    hoy_conviene = ofertas_top[:6]

    # Indicadores resumidos para la portada
    kpis = {
        "productos_monitoreados": Producto.objects.filter(activo=True).count(),
        "comercios_activos": Sucursal.objects.filter(activa=True, comercio__activo=True, comercio__estado="ACTIVO").count(),
        "ofertas_vigentes": Precio.objects.ofertas_vigentes().count(),
        "precios_registrados": Precio.objects.count(),
    }

    sucursales_mapa = list(
        Sucursal.objects.filter(activa=True, verificada_mapa=True, comercio__estado="ACTIVO")
        .select_related("comercio")[:35]
    )
    puntos_mini = [
        {
            "id": s.id,
            "nombre": s.nombre_visible,
            "tipo": s.comercio.get_tipo_display(),
            "direccion": s.direccion,
            "sector": s.sector,
            "lat": float(s.latitud),
            "lng": float(s.longitud),
        }
        for s in sucursales_mapa
    ]

    return render(
        request,
        "portal/inicio.html",
        {
            "categorias": categorias,
            "banners": banners,
            "hoy_conviene": hoy_conviene,
            "kpis": kpis,
            "ferias_hoy": obtener_ferias_por_dia(),
            "puntos_mapa_json": json.dumps(puntos_mini, ensure_ascii=False),
        },
    )


def vista_buscar(request):
    """
    Buscador y comparador rápido de productos (# REQ-04).
    Muestra el precio más bajo vigente, precio por unidad (kg/L/un) y cantidad de comercios.
    """
    q = request.GET.get("q", "").strip()
    cat_slug = request.GET.get("categoria", "").strip()
    sector = request.GET.get("sector", "").strip()
    solo_canasta = request.GET.get("canasta") == "1"
    orden = request.GET.get("orden", "precio_unidad")

    productos_qs = Producto.objects.filter(activo=True).select_related("categoria", "marca")
    if cat_slug:
        productos_qs = productos_qs.filter(categoria__slug=cat_slug)
    if solo_canasta:
        productos_qs = productos_qs.filter(es_canasta_basica=True)

    productos = [p for p in productos_qs if coincide_producto(p, q)]
    prod_ids = [p.id for p in productos]

    precios_qs = (
        Precio.objects.vigentes()
        .filter(producto_id__in=prod_ids)
        .select_related("producto", "producto__marca", "sucursal", "sucursal__comercio")
    )
    if sector:
        precios_qs = precios_qs.filter(sucursal__sector=sector)

    # Agrupar precios vigentes por producto para mostrar el mejor precio y resumen comparativo
    por_producto = defaultdict(list)
    for pr in precios_qs:
        por_producto[pr.producto_id].append(pr)

    resultados = []
    for prod in productos:
        lista_p = por_producto.get(prod.id, [])
        if not lista_p:
            continue
        lista_p.sort(key=lambda x: x.precio_vigente)
        mejor = lista_p[0]
        peor = lista_p[-1]
        resultados.append(
            {
                "producto": prod,
                "mejor_precio": mejor,
                "precio_min": mejor.precio_vigente,
                "precio_max": peor.precio_vigente,
                "ahorro_potencial": max(0, peor.precio_vigente - mejor.precio_vigente),
                "precio_por_unidad": mejor.precio_por_unidad,
                "cantidad_locales": len(lista_p),
                "fecha_obs": mejor.fecha_observacion,
            }
        )

    if orden == "precio":
        resultados.sort(key=lambda r: r["precio_min"])
    elif orden == "vigencia":
        resultados.sort(key=lambda r: r["fecha_obs"], reverse=True)
    else:
        resultados.sort(key=lambda r: r["precio_por_unidad"])

    return render(
        request,
        "portal/buscar.html",
        {
            "resultados": resultados[:60],
            "total_resultados": len(resultados),
            "categorias": Categoria.objects.filter(activa=True),
            "sectores": SECTORES_PAC,
            "q": q,
            "cat_slug": cat_slug,
            "sector": sector,
            "solo_canasta": solo_canasta,
            "orden": orden,
        },
    )


def vista_comparar_producto(request, producto_id):
    """
    Comparador detallado de un producto entre comercios + historial semanal Chart.js (# REQ-04, 06, 13).
    Incluye tabla alternativa accesible para el gráfico y formatos equivalentes del mismo producto.
    """
    producto = get_object_or_404(Producto.objects.select_related("categoria", "marca"), pk=producto_id, activo=True)
    orden = request.GET.get("orden", "precio")
    lat_str = request.GET.get("lat", "").strip()
    lng_str = request.GET.get("lng", "").strip()

    precios_vigentes = list(
        Precio.objects.vigentes()
        .filter(producto=producto)
        .select_related("sucursal", "sucursal__comercio")
    )

    # Integración con PostGIS/geo.cercanas cuando el usuario comparte ubicación (# REQ-04, Sección 1.5)
    distancias_por_sucursal = {}
    if lat_str and lng_str:
        try:
            from apps.comercios import geo

            lat_u, lng_u = float(lat_str), float(lng_str)
            for item in geo.cercanas(lat_u, lng_u, radio_m=20000, limite=200):
                distancias_por_sucursal[item["id_sucursal"]] = item["distancia_m"]
            for p in precios_vigentes:
                dm = distancias_por_sucursal.get(p.sucursal_id)
                p.distancia_m = dm
                p.distancia_texto = geo.formatear_distancia(dm)
        except (TypeError, ValueError):
            distancias_por_sucursal = {}

    if orden == "cercania" and distancias_por_sucursal:
        precios_vigentes.sort(key=lambda p: getattr(p, "distancia_m", None) if getattr(p, "distancia_m", None) is not None else 999999)
    elif orden == "unidad":
        precios_vigentes.sort(key=lambda p: p.precio_por_unidad)
    elif orden == "fecha":
        precios_vigentes.sort(key=lambda p: p.fecha_observacion, reverse=True)
    else:
        precios_vigentes.sort(key=lambda p: p.precio_vigente)

    mejor_precio = precios_vigentes[0] if precios_vigentes else None

    # Productos relacionados en distinto formato (ej. arroz 1 kg vs 500 g) para comparar por unidad (# REQ-01, 04)
    otros_formatos = list(
        Producto.objects.filter(nombre=producto.nombre, activo=True)
        .exclude(pk=producto.pk)
        .select_related("marca")[:6]
    )

    # Historial de precios (últimas 12 semanas) agrupado por fecha para Chart.js + tabla accesible (# REQ-06)
    historico_qs = (
        Precio.objects.filter(producto=producto)
        .exclude(estado=Precio.Estado.RECHAZADO)
        .values("fecha_observacion")
        .annotate(promedio=Avg("precio_normal"), minimo=Min("precio_normal"), muestras=Count("id"))
        .order_by("fecha_observacion")
    )
    serie_historial = [
        {
            "fecha": h["fecha_observacion"].strftime("%d/%m/%Y"),
            "promedio": round(float(h["promedio"] or 0)),
            "minimo": int(h["minimo"] or 0),
            "muestras": h["muestras"],
        }
        for h in historico_qs
    ]

    return render(
        request,
        "portal/comparar.html",
        {
            "producto": producto,
            "precios_vigentes": precios_vigentes,
            "mejor_precio": mejor_precio,
            "otros_formatos": otros_formatos,
            "serie_historial": serie_historial,
            "serie_historial_json": json.dumps(serie_historial, ensure_ascii=False),
            "orden": orden,
        },
    )


def vista_ofertas(request):
    """Listado de ofertas vigentes en Pedro Aguirre Cerda con ahorro y condiciones claras (# REQ-03, 04, 09)."""
    cat_slug = request.GET.get("categoria", "").strip()
    qs = Precio.objects.ofertas_vigentes().select_related(
        "producto", "producto__marca", "producto__categoria", "sucursal", "sucursal__comercio"
    )
    if cat_slug:
        qs = qs.filter(producto__categoria__slug=cat_slug)
    ofertas = list(qs[:120])
    ofertas.sort(key=lambda p: p.porcentaje_descuento, reverse=True)

    return render(
        request,
        "portal/ofertas.html",
        {
            "ofertas": ofertas,
            "categorias": Categoria.objects.filter(activa=True),
            "cat_slug": cat_slug,
        },
    )


def vista_mapa_comercios(request):
    """
    Mapa interactivo Leaflet + vista alternativa en listado (# REQ-05, REQ-12).
    """
    tipo = request.GET.get("tipo", "").strip()
    sector = request.GET.get("sector", "").strip()

    sucursales = Sucursal.objects.filter(
        activa=True, verificada_mapa=True, comercio__activo=True, comercio__estado="ACTIVO"
    ).select_related("comercio")

    if tipo:
        sucursales = sucursales.filter(comercio__tipo=tipo)
    if sector:
        sucursales = sucursales.filter(sector=sector)

    sucursales_lista = list(sucursales)
    puntos = [
        {
            "id": s.id,
            "nombre": s.nombre_visible,
            "tipo": s.comercio.get_tipo_display(),
            "direccion": s.direccion,
            "sector": s.sector,
            "horario": s.horario,
            "lat": float(s.latitud),
            "lng": float(s.longitud),
            "url": f"/comercio/{s.id}/",
        }
        for s in sucursales_lista
    ]

    return render(
        request,
        "portal/mapa.html",
        {
            "sucursales": sucursales_lista,
            "puntos_json": json.dumps(puntos, ensure_ascii=False),
            "tipos": Comercio.Tipo.choices,
            "sectores": SECTORES_PAC,
            "tipo_sel": tipo,
            "sector_sel": sector,
        },
    )


def vista_detalle_sucursal(request, sucursal_id):
    """Ficha pública de una sucursal con sus datos y precios vigentes (# REQ-02, REQ-05, REQ-13)."""
    sucursal = get_object_or_404(
        Sucursal.objects.select_related("comercio"),
        pk=sucursal_id,
        activa=True,
        comercio__estado="ACTIVO",
    )
    precios = (
        Precio.objects.vigentes()
        .filter(sucursal=sucursal)
        .select_related("producto", "producto__marca", "producto__categoria")
        .order_by("producto__categoria__orden", "producto__nombre")
    )
    return render(request, "portal/detalle_sucursal.html", {"sucursal": sucursal, "precios": precios})


def vista_transparencia(request):
    """Página 'Cómo funciona / Metodología y transparencia' (# REQ-13)."""
    return render(request, "portal/transparencia.html", {"hoy": timezone.localdate()})


def vista_faq(request):
    """Preguntas frecuentes en lenguaje sencillo."""
    return render(request, "portal/faq.html")


def vista_contacto(request):
    """Información de contacto académico y orientación a vecinos y comerciantes."""
    return render(request, "portal/contacto.html")


def vista_privacidad(request):
    """Borrador de aviso de privacidad conforme a Ley 19.628 y actualización Ley 21.719 (# II.11)."""
    return render(request, "portal/privacidad.html")
