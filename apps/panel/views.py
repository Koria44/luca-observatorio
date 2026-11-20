"""Vistas de dashboards diferenciados por rol (# REQ-07, REQ-08)."""
import json
from datetime import timedelta

from django.contrib.auth.decorators import login_required
from django.db.models import Avg, Count
from django.shortcuts import redirect, render
from django.utils import timezone

from apps.catalogo.models import Categoria
from apps.comercios.models import Comercio, Sucursal
from apps.cuentas.models import Usuario
from apps.nucleo.permisos import comerciante_activo_requerido, solo_admin, solo_fiscalizador_o_admin
from apps.nucleo.validadores import SECTORES_PAC
from apps.precios.models import Precio

from .servicios import calcular_indicadores


@login_required
def vista_panel_inicio(request):
    """Redirige al dashboard correspondiente según el rol del usuario autenticado."""
    u = request.user
    if u.rol == Usuario.Rol.ADMIN or u.is_superuser:
        return redirect("panel:admin")
    if u.rol == Usuario.Rol.FISCALIZADOR:
        return redirect("panel:fiscalizador")
    if u.rol == Usuario.Rol.COMERCIANTE:
        if u.estado_cuenta != Usuario.EstadoCuenta.ACTIVA:
            return redirect("cuentas:en_revision")
        return redirect("panel:comerciante")
    return redirect("portal:inicio")


@solo_admin
def vista_dashboard_admin(request):
    """Dashboard integral DIDESE con filtros globales, KPIs, gráficos y tablas de trabajo (# REQ-07)."""
    filtros = {
        "dias": request.GET.get("dias", "30"),
        "categoria": request.GET.get("categoria", ""),
        "sector": request.GET.get("sector", ""),
        "comercio": request.GET.get("comercio", ""),
    }
    datos = calcular_indicadores(filtros)

    serie_categorias = [{"etiqueta": c["etiqueta"], "valor": c["promedio"]} for c in datos["por_categoria"]]
    return render(
        request,
        "panel/dashboard_admin.html",
        {
            "datos": datos,
            "filtros": filtros,
            "categorias": Categoria.objects.filter(activa=True),
            "comercios": Comercio.objects.filter(activo=True, estado="ACTIVO"),
            "sectores": SECTORES_PAC,
            "serie_categorias_json": json.dumps(serie_categorias, ensure_ascii=False),
            "serie_comercios_json": json.dumps(datos["por_comercio"], ensure_ascii=False),
        },
    )


@solo_fiscalizador_o_admin
def vista_dashboard_fiscalizador(request):
    """Dashboard operativo del fiscalizador municipal (# REQ-08, REQ-09)."""
    cuentas_pend = Usuario.objects.filter(
        rol=Usuario.Rol.COMERCIANTE, estado_cuenta=Usuario.EstadoCuenta.PENDIENTE
    ).count()
    precios_pend = Precio.objects.filter(estado=Precio.Estado.PENDIENTE).count()
    alertas = Precio.objects.filter(alerta_variacion=True, estado=Precio.Estado.PENDIENTE).count()
    return render(
        request,
        "panel/dashboard_fiscalizador.html",
        {"cuentas_pend": cuentas_pend, "precios_pend": precios_pend, "alertas": alertas},
    )


@comerciante_activo_requerido
def vista_dashboard_comerciante(request):
    """
    Dashboard del comerciante activo (# REQ-08):
    - Estado de precios, ofertas por vencer (<= 48 h) y desactualizados (> 14 días) con 1-clic.
    - Comparativa privada vs. promedio comunal (sin revelar datos de competidores).
    """
    hoy = timezone.localdate()
    qs = Precio.objects.filter(sucursal__comercio__propietario=request.user).select_related(
        "producto", "producto__marca", "sucursal"
    )
    publicados = list(qs.filter(estado=Precio.Estado.PUBLICADO)[:60])

    por_vencer = [
        p for p in publicados
        if p.vigencia_hasta and hoy <= p.vigencia_hasta <= (hoy + timedelta(days=2))
    ]
    desactualizados = [
        p for p in publicados
        if (hoy - p.fecha_observacion).days > 14
    ]

    # Comparativa privada contra promedio comunal de cada producto (anónima)
    prod_ids = [p.producto_id for p in publicados[:15]]
    promedios_comuna = {
        row["producto_id"]: round(float(row["prom"] or 0))
        for row in Precio.objects.vigentes()
        .filter(producto_id__in=prod_ids)
        .values("producto_id")
        .annotate(prom=Avg("precio_normal"))
    }
    comparativa_privada = []
    vistos = set()
    for p in publicados[:15]:
        if p.producto_id in vistos:
            continue
        vistos.add(p.producto_id)
        prom = promedios_comuna.get(p.producto_id)
        if not prom:
            continue
        diff_pct = round(((p.precio_vigente - prom) / prom) * 100, 1)
        if diff_pct <= -3:
            estado_comp = ("Bajo el promedio", "text-verde-700", "▼")
        elif diff_pct >= 3:
            estado_comp = ("Sobre el promedio", "text-rojo-600", "▲")
        else:
            estado_comp = ("En el promedio", "text-marino-900", "●")
        comparativa_privada.append(
            {
                "precio": p,
                "promedio_comuna": prom,
                "diff_pct": diff_pct,
                "etiqueta": estado_comp[0],
                "clase": estado_comp[1],
                "flecha": estado_comp[2],
            }
        )

    resumen = {
        "vigentes": qs.filter(estado=Precio.Estado.PUBLICADO).count(),
        "pendientes": qs.filter(estado=Precio.Estado.PENDIENTE).count(),
        "rechazados": qs.filter(estado=Precio.Estado.RECHAZADO).count(),
        "ultimos": qs[:10],
        "por_vencer": por_vencer[:10],
        "desactualizados": desactualizados[:10],
        "comparativa_privada": comparativa_privada,
    }
    return render(request, "panel/dashboard_comerciante.html", {"resumen": resumen})


@solo_admin
def vista_cobertura_didese(request):
    """
    Mapa de cobertura y detección de 'desiertos de monitoreo' por sector de Pedro Aguirre Cerda
    (# Funcionalidad DIDESE sobre PostGIS + MapLibre + tabla accesible).
    """
    sectores_stats = []
    for valor, etiqueta in SECTORES_PAC:
        if valor == "Otro sector PAC":
            continue
        sucs = Sucursal.objects.filter(
            sector=valor, activa=True, comercio__activo=True, comercio__estado="ACTIVO"
        )
        cnt_locales = sucs.count()
        agg_precios = Precio.objects.vigentes().filter(sucursal__sector=valor).aggregate(
            promedio=Avg("precio_normal"),
            productos=Count("producto_id", distinct=True),
        )
        coord_ref = sucs.first()
        sectores_stats.append(
            {
                "sector": valor,
                "etiqueta": etiqueta,
                "locales": cnt_locales,
                "productos": agg_precios["productos"] or 0,
                "precio_promedio": round(float(agg_precios["promedio"] or 0)),
                "es_desierto": cnt_locales <= 2,
                "lat": float(coord_ref.latitud) if coord_ref else -33.491,
                "lng": float(coord_ref.longitud) if coord_ref else -70.6745,
            }
        )

    sectores_stats.sort(key=lambda s: s["locales"])
    return render(
        request,
        "panel/cobertura_didese.html",
        {
            "sectores_stats": sectores_stats,
            "sectores_json": json.dumps(sectores_stats, ensure_ascii=False),
            "desiertos_count": sum(1 for s in sectores_stats if s["es_desierto"]),
        },
    )
