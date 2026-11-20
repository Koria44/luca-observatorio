"""
Servicio único de cálculo de indicadores del observatorio (# REQ-07, REQ-14).

Tanto el Dashboard DIDESE (`apps/panel/views.py`) como los reportes Excel y PDF
(`apps/reportes/views.py`) consumen exactamente esta función `calcular_indicadores(filtros)`
para garantizar que lo exportado coincida al 100 % con lo mostrado en pantalla.
"""
from datetime import timedelta

from django.db.models import Avg, Count, Max, Min
from django.utils import timezone

from apps.catalogo.models import Categoria
from apps.comercios.geo_proxy import obtener_consumo_diario_mapas
from apps.comercios.models import Comercio, Sucursal
from apps.cuentas.models import Usuario
from apps.nucleo.validadores import SECTORES_PAC
from apps.precios.models import Precio


def calcular_indicadores(filtros: dict | None = None) -> dict:
    """Calcula KPIs, canasta básica, cobertura por sector y series comparativas."""
    filtros = filtros or {}
    hoy = timezone.localdate()

    try:
        dias = int(filtros.get("dias") or 30)
    except (TypeError, ValueError):
        dias = 30
    if dias not in (7, 30, 90, 365):
        dias = 30
    fecha_inicio = hoy - timedelta(days=dias)

    cat_slug = (filtros.get("categoria") or "").strip()
    sector = (filtros.get("sector") or "").strip()
    comercio_id = (filtros.get("comercio") or "").strip()

    precios_vig = Precio.objects.vigentes().filter(fecha_observacion__gte=fecha_inicio)
    sucursales_act = Sucursal.objects.filter(activa=True, comercio__activo=True, comercio__estado="ACTIVO")

    categoria_nombre = "Todas las categorías"
    if cat_slug:
        precios_vig = precios_vig.filter(producto__categoria__slug=cat_slug)
        cat_obj = Categoria.objects.filter(slug=cat_slug).first()
        if cat_obj:
            categoria_nombre = cat_obj.nombre

    if sector:
        precios_vig = precios_vig.filter(sucursal__sector=sector)
        sucursales_act = sucursales_act.filter(sector=sector)

    comercio_nombre = "Todos los comercios"
    if comercio_id.isdigit():
        precios_vig = precios_vig.filter(sucursal__comercio_id=int(comercio_id))
        sucursales_act = sucursales_act.filter(comercio_id=int(comercio_id))
        com_obj = Comercio.objects.filter(pk=int(comercio_id)).first()
        if com_obj:
            comercio_nombre = com_obj.nombre_fantasia

    agregados = precios_vig.aggregate(
        prom=Avg("precio_normal"),
        minimo=Min("precio_normal"),
        maximo=Max("precio_normal"),
        total_reg=Count("id"),
        productos_dist=Count("producto_id", distinct=True),
    )

    # Costo de la canasta básica (suma del precio mínimo, promedio y máximo de cada ítem de canasta)
    canasta_qs = (
        precios_vig.filter(producto__es_canasta_basica=True)
        .values("producto_id")
        .annotate(p_min=Min("precio_normal"), p_prom=Avg("precio_normal"), p_max=Max("precio_normal"))
    )
    canasta_min = sum(int(c["p_min"] or 0) for c in canasta_qs)
    canasta_prom = sum(round(float(c["p_prom"] or 0)) for c in canasta_qs)
    canasta_max = sum(int(c["p_max"] or 0) for c in canasta_qs)

    # Cobertura por sector de Pedro Aguirre Cerda
    total_sectores = max(1, len(SECTORES_PAC) - 1)  # excluye "Otro sector"
    sectores_cubiertos = sucursales_act.values("sector").distinct().count()
    cobertura_pct = min(100, round((sectores_cubiertos / total_sectores) * 100))

    # Antigüedad promedio del dato en días
    fechas = list(precios_vig.values_list("fecha_observacion", flat=True)[:500])
    antiguedad_dias = (
        round(sum((hoy - f).days for f in fechas) / len(fechas), 1) if fechas else 0.0
    )

    # Desglose por categoría (para gráficos, tabla accesible y reportes Excel/PDF)
    por_categoria = [
        {
            "etiqueta": row["producto__categoria__nombre"],
            "promedio": round(float(row["promedio"] or 0)),
            "minimo": int(row["minimo"] or 0),
            "maximo": int(row["maximo"] or 0),
            "cantidad": row["cantidad"],
        }
        for row in (
            precios_vig.values("producto__categoria__nombre")
            .annotate(
                promedio=Avg("precio_normal"),
                minimo=Min("precio_normal"),
                maximo=Max("precio_normal"),
                cantidad=Count("id"),
            )
            .order_by("producto__categoria__nombre")
        )
    ]

    # Top 10 comercios por precio promedio observado
    por_comercio = [
        {
            "etiqueta": row["sucursal__comercio__nombre_fantasia"],
            "valor": round(float(row["promedio"] or 0)),
            "cantidad": row["cantidad"],
        }
        for row in (
            precios_vig.values("sucursal__comercio__nombre_fantasia")
            .annotate(promedio=Avg("precio_normal"), cantidad=Count("id"))
            .order_by("promedio")[:10]
        )
    ]

    return {
        "fecha_generacion": timezone.localtime(),
        "periodo_desde": fecha_inicio,
        "periodo_hasta": hoy,
        "filtros_legibles": {
            "dias": dias,
            "periodo": f"Últimos {dias} días ({fecha_inicio:%d/%m/%Y} – {hoy:%d/%m/%Y})",
            "categoria": categoria_nombre,
            "sector": sector or "Toda la comuna",
            "comercio": comercio_nombre,
        },
        "kpis": {
            "canasta_min": canasta_min,
            "canasta_prom": canasta_prom,
            "canasta_max": canasta_max,
            "canasta_items": len(canasta_qs),
            "precio_promedio": round(float(agregados["prom"] or 0)),
            "precio_minimo": int(agregados["minimo"] or 0),
            "precio_maximo": int(agregados["maximo"] or 0),
            "ofertas_vigentes": precios_vig.filter(precio_oferta__isnull=False).count(),
            "productos_monitoreados": agregados["productos_dist"] or 0,
            "comercios_activos": sucursales_act.count(),
            "cobertura_sectores_pct": cobertura_pct,
            "antiguedad_promedio_dias": antiguedad_dias,
            "total_registros_vigentes": agregados["total_reg"] or 0,
        },
        "por_categoria": por_categoria,
        "por_comercio": por_comercio,
        "consumo_mapas": obtener_consumo_diario_mapas(),
        "tablas_trabajo": {
            "cuentas_pendientes": Usuario.objects.filter(
                rol=Usuario.Rol.COMERCIANTE,
                estado_cuenta__in=[Usuario.EstadoCuenta.PENDIENTE, Usuario.EstadoCuenta.VERIFICADA],
            ).count(),
            "precios_pendientes": Precio.objects.filter(estado=Precio.Estado.PENDIENTE).count(),
            "alertas_atipicas": list(
                Precio.objects.filter(alerta_variacion=True)
                .select_related("producto", "producto__marca", "sucursal", "sucursal__comercio")
                .order_by("-creado_en")[:10]
            ),
        },
    }
