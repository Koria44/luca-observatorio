"""Vistas y rutas de la lista de verificación de los 16 requerimientos."""
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.nucleo.permisos import solo_admin, solo_fiscalizador_o_admin

from .models import VerificacionRequisito


@solo_fiscalizador_o_admin
def lista_verificacion(request):
    items = VerificacionRequisito.objects.select_related("verificado_por").all()
    cumplidos = items.filter(estado=VerificacionRequisito.Estado.CUMPLIDO).count()
    return render(
        request,
        "verificacion/lista.html",
        {"items": items, "cumplidos": cumplidos, "total": items.count()},
    )


@solo_admin
@require_POST
def actualizar_requisito(request, numero):
    item = get_object_or_404(VerificacionRequisito, numero=numero)
    nuevo_estado = request.POST.get("estado", VerificacionRequisito.Estado.PENDIENTE)
    evidencia = request.POST.get("evidencia", "").strip()
    comentario = request.POST.get("comentario", "").strip()

    # Criterio oficial: no marcar CUMPLIDO sin evidencia documentada
    if nuevo_estado == VerificacionRequisito.Estado.CUMPLIDO and not evidencia:
        messages.error(request, f"REQ-{numero:02d} no puede marcarse CUMPLIDO sin registrar evidencia.")
        return redirect("verificacion:lista")

    item.estado = nuevo_estado
    item.evidencia = evidencia
    item.comentario = comentario
    item.verificado_por = request.user
    item.save()
    messages.success(request, f"REQ-{numero:02d} actualizado a {item.get_estado_display()}.")
    return redirect("verificacion:lista")
