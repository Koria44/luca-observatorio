"""
Vistas de gestión de comercios y sucursales (# REQ-02, REQ-08).

# SEGURIDAD (IDOR): Un comerciante activo solo puede ver y editar sus propios comercios
y sucursales. Cualquier intento de acceder o modificar un recurso ajeno responde 403
y queda registrado en auditoría.
"""
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect, render

from apps.nucleo.permisos import comerciante_activo_requerido, solo_admin

from .forms import FormularioComercio, FormularioSucursal
from .models import Comercio, Sucursal


def _auditar_intento_idor(request, modelo: str, objeto_id):
    try:
        from apps.auditoria.servicios import registrar_auditoria

        registrar_auditoria(
            usuario=request.user,
            accion="RECHAZAR",
            modelo=modelo,
            objeto_id=str(objeto_id),
            valores_nuevos={"motivo": "Intento de acceso a recurso ajeno (IDOR bloqueado)"},
            request=request,
        )
    except Exception:
        pass


@comerciante_activo_requerido
def mis_sucursales(request):
    """Lista los comercios y sucursales del comerciante (o todos si es ADMIN)."""
    if request.user.rol == "ADMIN" or request.user.is_superuser:
        comercios = Comercio.objects.prefetch_related("sucursales").all()
    else:
        comercios = Comercio.objects.prefetch_related("sucursales").filter(propietario=request.user)
    return render(request, "comercios/mis_sucursales.html", {"comercios": comercios})


@comerciante_activo_requerido
def editar_sucursal(request, pk):
    """Edita una sucursal verificando estrictamente la propiedad (# SEGURIDAD / IDOR)."""
    sucursal = get_object_or_404(Sucursal.objects.select_related("comercio"), pk=pk)
    es_admin = request.user.rol == "ADMIN" or request.user.is_superuser
    if not es_admin and sucursal.comercio.propietario_id != request.user.id:
        _auditar_intento_idor(request, "Sucursal", sucursal.pk)
        raise PermissionDenied("No tienes permiso para modificar una sucursal de otro comercio.")

    form = FormularioSucursal(request.POST or None, instance=sucursal)
    if request.method == "POST" and form.is_valid():
        anteriores = {
            "direccion": sucursal.direccion,
            "latitud": str(sucursal.latitud),
            "longitud": str(sucursal.longitud),
            "fuera_de_comuna": sucursal.fuera_de_comuna,
        }
        suc_guardada = form.save()
        if request.user.es_staff_observatorio:
            from django.utils import timezone

            suc_guardada.ubicacion_verificada = True
            suc_guardada.verificada_por = request.user
            suc_guardada.fecha_verificacion = timezone.now()
            suc_guardada.save(update_fields=["ubicacion_verificada", "verificada_por", "fecha_verificacion"])

        try:
            from apps.auditoria.servicios import registrar_auditoria

            registrar_auditoria(
                usuario=request.user,
                accion="MODIFICAR",
                modelo="Sucursal",
                objeto_id=str(suc_guardada.pk),
                valores_anteriores=anteriores,
                valores_nuevos={
                    "direccion": suc_guardada.direccion,
                    "latitud": str(suc_guardada.latitud),
                    "longitud": str(suc_guardada.longitud),
                    "fuera_de_comuna": suc_guardada.fuera_de_comuna,
                },
                request=request,
            )
        except Exception:
            pass

        if suc_guardada.fuera_de_comuna:
            messages.warning(
                request,
                f"Sucursal '{suc_guardada.nombre}' guardada, pero las coordenadas quedaron FUERA del límite de Pedro Aguirre Cerda (se notificará al fiscalizador).",
            )
        else:
            messages.success(request, f"Sucursal '{suc_guardada.nombre}' actualizada correctamente.")
        return redirect("comercios:mis_sucursales")
    return render(request, "comercios/formulario_sucursal.html", {"form": form, "sucursal": sucursal})


@solo_admin
def crear_comercio(request):
    form = FormularioComercio(request.POST or None)
    if request.method == "POST" and form.is_valid():
        comercio = form.save()
        messages.success(request, f"Comercio '{comercio.nombre_fantasia}' registrado.")
        return redirect("comercios:mis_sucursales")
    return render(request, "comercios/formulario_comercio.html", {"form": form})
