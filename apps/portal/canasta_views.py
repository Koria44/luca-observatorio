"""
Vistas ciudadanas de Mi Lista de Compras / Canasta Personal, Alertas de baja de precio,
Ferias abiertas HOY y Reporte ciudadano de precio en sala.
"""
import json

from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.html import strip_tags
from django.views.decorators.http import require_POST

from apps.catalogo.models import Producto
from apps.nucleo.permisos import rol_requerido
from apps.nucleo.validadores import SECTORES_PAC, validar_precio_clp
from apps.precios.models import AlertaPrecio, CanastaItem, Precio, ReportePrecio

from .canasta_optimizador import calcular_optimizacion_canasta
from .ferias import obtener_ferias_por_dia


@rol_requerido("VECINO")
def vista_mi_canasta(request):
    """Página privada de Mi Lista de Compras / Canasta Personal (exclusiva para rol VECINO)."""
    items_iniciales = [
        {"producto_id": ci.producto_id, "nombre": ci.producto.nombre_completo, "cantidad": ci.cantidad}
        for ci in CanastaItem.objects.filter(usuario=request.user).select_related("producto", "producto__marca")
    ]
    productos_sugeridos = Producto.objects.filter(activo=True, es_canasta_basica=True).select_related("marca")[:20]
    return render(
        request,
        "portal/mi_canasta.html",
        {
            "items_iniciales_json": json.dumps(items_iniciales, ensure_ascii=False),
            "productos_sugeridos": productos_sugeridos,
        },
    )


@rol_requerido("VECINO")
@require_POST
def api_agregar_item_canasta(request):
    """Agrega o incrementa un producto en la canasta personal del vecino autenticado."""
    try:
        payload = json.loads(request.body.decode("utf-8"))
        pid = int(payload.get("producto_id", 0))
    except Exception:
        return JsonResponse({"error": "Solicitud inválida."}, status=400)

    producto = get_object_or_404(Producto, pk=pid, activo=True)
    item, creado = CanastaItem.objects.get_or_create(
        usuario=request.user, producto=producto, defaults={"cantidad": 1}
    )
    if not creado:
        item.cantidad = min(20, item.cantidad + 1)
        item.save(update_fields=["cantidad"])

    total_items = sum(CanastaItem.objects.filter(usuario=request.user).values_list("cantidad", flat=True))
    return JsonResponse({"ok": True, "total_items": total_items})


@rol_requerido("VECINO")
@require_POST
def api_calcular_canasta(request):
    """Calcula y persiste la lista de compras estrictamente para el vecino autenticado."""
    try:
        payload = json.loads(request.body.decode("utf-8"))
        items = payload.get("items", [])
        umbral_desvio = payload.get("umbral_desvio", 500)
        max_locales = payload.get("max_locales", 3)
    except Exception:
        return JsonResponse({"error": "Formato JSON inválido."}, status=400)

    ids_validos = set()
    for it in items[:30]:
        try:
            pid = int(it["producto_id"])
            cant = max(1, min(20, int(it.get("cantidad", 1))))
            if Producto.objects.filter(pk=pid, activo=True).exists():
                CanastaItem.objects.update_or_create(
                    usuario=request.user, producto_id=pid, defaults={"cantidad": cant}
                )
                ids_validos.add(pid)
        except (KeyError, TypeError, ValueError):
            continue
    CanastaItem.objects.filter(usuario=request.user).exclude(producto_id__in=ids_validos).delete()

    sector_pref = getattr(request.user, "sector", "") or ""
    resultado = calcular_optimizacion_canasta(
        items,
        umbral_desvio=umbral_desvio,
        max_locales=max_locales,
        sector_preferido=sector_pref,
    )
    return JsonResponse(resultado)


@rol_requerido("VECINO")
def vista_alertas_precio(request):
    """Gestión de alertas personales de baja de precio."""
    if request.method == "POST":
        accion = request.POST.get("accion", "crear")
        if accion == "eliminar":
            alerta_id = request.POST.get("alerta_id")
            AlertaPrecio.objects.filter(pk=alerta_id, usuario=request.user).delete()
            messages.info(request, "Alerta eliminada.")
            return redirect("portal:alertas_precio")

        prod_id = request.POST.get("producto_id", "")
        precio_obj = request.POST.get("precio_objetivo", "")
        sector = request.POST.get("sector", "").strip()
        try:
            producto = get_object_or_404(Producto, pk=int(prod_id), activo=True)
            monto = int(precio_obj)
            validar_precio_clp(monto)
            AlertaPrecio.objects.create(
                usuario=request.user, producto=producto, precio_objetivo=monto, sector=sector, activa=True
            )
            messages.success(
                request,
                f"✔ Alerta creada: te avisaremos por correo cuando {producto.nombre_completo} baje de ${monto:,}.",
            )
            return redirect("portal:alertas_precio")
        except Exception:
            messages.error(request, "Revisa el producto y el precio objetivo (entero mayor a $0).")

    alertas = AlertaPrecio.objects.filter(usuario=request.user).select_related("producto", "producto__marca")
    productos = Producto.objects.filter(activo=True).select_related("marca")[:180]
    prod_pre = request.GET.get("producto", "").strip()
    prod_pre_id = int(prod_pre) if prod_pre.isdigit() else None
    return render(
        request,
        "portal/alertas_precio.html",
        {
            "alertas": alertas,
            "productos": productos,
            "sectores": SECTORES_PAC,
            "producto_preseleccionado": prod_pre_id,
        },
    )


def vista_ferias_hoy(request):
    """Muestra qué Ferias Libres de Pedro Aguirre Cerda funcionan HOY y el calendario semanal."""
    dia_param = request.GET.get("dia", "").strip()
    dia_idx = int(dia_param) if dia_param.isdigit() else None
    datos = obtener_ferias_por_dia(dia_idx)
    return render(request, "portal/ferias_hoy.html", datos)


@rol_requerido("VECINO")
@require_POST
def vista_reportar_precio(request, precio_id):
    """Permite a un vecino autenticado reportar una discrepancia de precio o stock en sala."""
    precio = get_object_or_404(Precio, pk=precio_id)
    motivo = request.POST.get("motivo", ReportePrecio.Motivo.PRECIO_DISTINTO)
    if motivo not in dict(ReportePrecio.Motivo.choices):
        motivo = ReportePrecio.Motivo.PRECIO_DISTINTO
    comentario = strip_tags(request.POST.get("comentario", "")).strip()[:240]
    ReportePrecio.objects.create(
        precio=precio,
        motivo=motivo,
        comentario=comentario,
        reportado_por=request.user if request.user.is_authenticated else None,
    )
    messages.info(request, "✔ Reporte recibido. Un fiscalizador revisará este precio.")
    return redirect("portal:comparar", producto_id=precio.producto_id)
