"""Vistas de registro de precios, historial propio, revisión municipal y cron (# REQ-03, 06, 09)."""
from django.conf import settings
from django.contrib import messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from apps.nucleo.permisos import (
    comerciante_activo_requerido,
    rol_requerido,
    solo_fiscalizador_o_admin,
)

from .forms import FormularioPrecio
from .models import Precio, ReportePrecio
from .servicios import (
    aprobar_precio,
    expirar_ofertas_vencidas,
    rechazar_precio,
    registrar_o_actualizar_precio,
)


@rol_requerido("COMERCIANTE", "FISCALIZADOR", "ADMIN")
def vista_registrar_precio(request):
    """Formulario guiado para publicar o actualizar un precio (# REQ-03)."""
    form = FormularioPrecio(request.POST or None, usuario=request.user)
    if request.method == "POST" and form.is_valid():
        d = form.cleaned_data
        sucursal = d["sucursal"]
        # SEGURIDAD (IDOR): Re-verificar propiedad en servidor si es comerciante
        if request.user.rol == "COMERCIANTE" and sucursal.comercio.propietario_id != request.user.id:
            raise PermissionDenied("No puedes publicar precios para una sucursal que no te pertenece.")

        fuente = (
            Precio.Fuente.FISCALIZADOR
            if request.user.rol in ("FISCALIZADOR", "ADMIN")
            else Precio.Fuente.COMERCIANTE
        )
        try:
            nuevo = registrar_o_actualizar_precio(
                producto=d["producto"],
                sucursal=sucursal,
                precio_normal=d["precio_normal"],
                precio_oferta=d.get("precio_oferta"),
                vigencia_desde=d.get("vigencia_desde"),
                vigencia_hasta=d.get("vigencia_hasta"),
                compra_minima=d.get("compra_minima"),
                medio_pago=d.get("medio_pago", ""),
                requiere_membresia=d.get("requiere_membresia", False),
                nombre_membresia=d.get("nombre_membresia", ""),
                condiciones=d.get("condiciones", ""),
                stock_confirmado=d.get("stock_confirmado", False),
                fuente=fuente,
                registrado_por=request.user,
                request=request,
            )
            if nuevo.alerta_variacion:
                messages.warning(
                    request,
                    f"Precio guardado en REVISIÓN: detectamos una variación de {nuevo.variacion_porcentual}% respecto al precio anterior.",
                )
            elif nuevo.estado == Precio.Estado.PUBLICADO:
                messages.success(request, "Precio publicado correctamente. El precio anterior quedó guardado en el historial.")
            else:
                messages.info(request, "Precio enviado a revisión municipal antes de publicarse.")
            return redirect("precios:mis_precios")
        except ValidationError as exc:
            form.add_error(None, exc)

    return render(request, "precios/registrar.html", {"form": form, "modo_terreno": False})


@solo_fiscalizador_o_admin
def vista_registro_terreno(request):
    """Formulario compacto optimizado para fiscalizadores en terreno móvil (# II.9)."""
    form = FormularioPrecio(request.POST or None, usuario=request.user)
    if request.method == "POST" and form.is_valid():
        d = form.cleaned_data
        try:
            registrar_o_actualizar_precio(
                producto=d["producto"],
                sucursal=d["sucursal"],
                precio_normal=d["precio_normal"],
                precio_oferta=d.get("precio_oferta"),
                vigencia_desde=d.get("vigencia_desde"),
                vigencia_hasta=d.get("vigencia_hasta"),
                stock_confirmado=True,
                fuente=Precio.Fuente.FISCALIZADOR,
                fuente_detalle="Levantamiento presencial en terreno (DIDESE PAC)",
                registrado_por=request.user,
                request=request,
            )
            messages.success(request, "Precio de terreno registrado y publicado.")
            return redirect("precios:terreno")
        except ValidationError as exc:
            form.add_error(None, exc)
    return render(request, "precios/registrar.html", {"form": form, "modo_terreno": True})


@rol_requerido("COMERCIANTE", "FISCALIZADOR", "ADMIN")
def vista_mis_precios(request):
    """Historial y estado de precios del comerciante (o últimos ingresados para staff)."""
    qs = Precio.objects.select_related("producto", "producto__marca", "sucursal", "sucursal__comercio")
    if request.user.rol == "COMERCIANTE":
        qs = qs.filter(sucursal__comercio__propietario=request.user)
    return render(request, "precios/mis_precios.html", {"precios": qs[:100]})


@solo_fiscalizador_o_admin
def vista_cola_revision_precios(request):
    """Cola de precios pendientes, alertas atípicas (> ±40 %) y reportes ciudadanos en sala (# REQ-09)."""
    pendientes = (
        Precio.objects.filter(estado=Precio.Estado.PENDIENTE)
        .select_related("producto", "producto__marca", "sucursal", "sucursal__comercio", "registrado_por")
        .order_by("-alerta_variacion", "-creado_en")
    )
    reportes_ciudadanos = (
        ReportePrecio.objects.filter(atendido=False)
        .select_related("precio", "precio__producto", "precio__producto__marca", "precio__sucursal", "precio__sucursal__comercio")
        .order_by("-creado_en")[:50]
    )
    return render(
        request,
        "precios/cola_revision.html",
        {"pendientes": pendientes[:100], "reportes_ciudadanos": reportes_ciudadanos},
    )


@solo_fiscalizador_o_admin
@require_POST
def vista_atender_reporte_precio(request, pk):
    """Marca un reporte ciudadano de precio en sala como atendido."""
    rep = get_object_or_404(ReportePrecio, pk=pk)
    rep.atendido = True
    rep.atendido_por = request.user
    rep.save(update_fields=["atendido", "atendido_por"])
    messages.success(request, f"Reporte ciudadano #{rep.pk} marcado como atendido.")
    return redirect("precios:cola_revision")


@comerciante_activo_requerido
@require_POST
def vista_confirmar_vigencia(request, pk):
    """Permite al comerciante confirmar en 1 clic que un precio publicado sigue vigente hoy."""
    from django.utils import timezone

    from apps.auditoria.servicios import registrar_auditoria

    precio = get_object_or_404(Precio.objects.select_related("sucursal", "sucursal__comercio"), pk=pk)
    es_admin = request.user.rol == "ADMIN" or request.user.is_superuser
    if not es_admin and precio.sucursal.comercio.propietario_id != request.user.id:
        raise PermissionDenied("No puedes confirmar precios de otro comercio.")

    fecha_ant = str(precio.fecha_observacion)
    precio.fecha_observacion = timezone.localdate()
    precio.save(update_fields=["fecha_observacion", "actualizado_en"])
    registrar_auditoria(
        usuario=request.user,
        accion="MODIFICAR",
        modelo="Precio",
        objeto_id=str(precio.pk),
        valores_anteriores={"fecha_observacion": fecha_ant},
        valores_nuevos={"fecha_observacion": str(precio.fecha_observacion), "accion": "confirmar_vigencia_1_clic"},
        request=request,
    )
    messages.success(request, f"✔ Vigencia de '{precio.producto.nombre_completo}' confirmada al día de hoy.")
    return redirect("panel:comerciante")


@solo_fiscalizador_o_admin
@require_POST
def vista_decidir_precio(request, pk):
    """Aprueba o rechaza un precio pendiente."""
    precio = get_object_or_404(Precio, pk=pk)
    accion = request.POST.get("accion")
    if accion == "aprobar":
        aprobar_precio(precio, request.user, request=request)
        messages.success(request, f"Precio de {precio.producto.nombre_completo} aprobado y publicado.")
    elif accion == "rechazar":
        motivo = request.POST.get("motivo", "").strip()
        try:
            rechazar_precio(precio, request.user, motivo, request=request)
            messages.warning(request, "Precio rechazado con motivo registrado.")
        except ValidationError as exc:
            messages.error(request, exc.message)
    return redirect("precios:cola_revision")


@csrf_exempt
def vista_cron_expirar_ofertas(request):
    """
    Endpoint para Vercel Cron que marca ofertas vencidas y registra auditoría (# REQ-09).
    # SEGURIDAD: Protegido mediante token `CRON_SECRET`.
    """
    secreto = getattr(settings, "CRON_SECRET", "")
    header_auth = request.headers.get("Authorization", "")
    token = request.headers.get("X-Cron-Secret") or header_auth.replace("Bearer ", "").strip()
    if not secreto or token != secreto:
        return JsonResponse({"error": "No autorizado."}, status=403)
    cantidad = expirar_ofertas_vencidas(request=request)
    return JsonResponse({"ok": True, "ofertas_expiradas": cantidad})
