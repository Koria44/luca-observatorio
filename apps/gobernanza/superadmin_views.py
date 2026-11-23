"""
Vistas exclusivas del Panel Superadmin (`/superadmin/`) (# Prompt 8 Sección 4).
# SEGURIDAD: Todas las vistas usan `@solo_superadmin` -> devuelven HTTP 404 a cualquier otro rol o anónimo.
"""
from django.contrib import messages
from django.contrib.sessions.models import Session
from django.core.exceptions import PermissionDenied, ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.auditoria.models import RegistroAuditoria
from apps.auditoria.servicios import registrar_auditoria, verificar_integridad_auditoria
from apps.cuentas.models import Usuario
from apps.gobernanza.models import ConfiguracionObservatorio, ElevacionSuperadmin
from apps.gobernanza.transiciones import (
    activar_elevacion_superadmin,
    cambiar_rol_usuario,
    configurar_kill_switch,
    revocar_elevacion_superadmin,
)
from apps.nucleo.middleware import cerrar_sesiones_usuario
from apps.nucleo.permisos import solo_superadmin


@solo_superadmin
def panel_superadmin(request):
    """Panel de gobierno técnico, seguridad, usuarios, auditoría exclusiva y elevación temporal."""
    usuarios = Usuario.objects.all().order_by("rol", "email")[:100]
    cfg = ConfiguracionObservatorio.obtener()
    elevacion = ElevacionSuperadmin.activa_para(request.user)
    sesiones_activas = Session.objects.filter(expire_date__gte=timezone.now()).count()
    total_auditoria = RegistroAuditoria.objects.count()
    denegados_recientes = RegistroAuditoria.objects.filter(accion=RegistroAuditoria.Accion.DENEGADO).count()

    return render(
        request,
        "superadmin/panel.html",
        {
            "usuarios": usuarios,
            "roles": Usuario.Rol.choices,
            "cfg": cfg,
            "elevacion": elevacion,
            "sesiones_activas": sesiones_activas,
            "total_auditoria": total_auditoria,
            "denegados_recientes": denegados_recientes,
        },
    )


@solo_superadmin
@require_POST
def accion_elevacion(request):
    """Activa o revoca la elevación temporal de 30 min para acciones operativas de negocio."""
    accion = request.POST.get("accion", "activar")
    if accion == "revocar":
        revocar_elevacion_superadmin(superadmin=request.user, request=request)
        messages.info(request, "Elevación temporal revocada.")
        return redirect("superadmin:panel")

    motivo = request.POST.get("motivo", "")
    codigo_totp = request.POST.get("codigo_totp", "")
    try:
        elev = activar_elevacion_superadmin(
            superadmin=request.user, motivo=motivo, codigo_totp=codigo_totp, minutos=30, request=request
        )
        messages.success(
            request,
            f"Elevación temporal activada hasta {elev.activa_hasta.strftime('%H:%M')} (máx. 30 min).",
        )
    except (ValidationError, PermissionDenied) as exc:
        messages.error(request, str(exc))
    return redirect("superadmin:panel")


@solo_superadmin
@require_POST
def accion_cambiar_rol(request, usuario_id):
    """Cambia el rol de un usuario con cierre inmediato de sesiones y auditoría."""
    objetivo = get_object_or_404(Usuario, pk=usuario_id)
    nuevo_rol = request.POST.get("nuevo_rol", "")
    motivo = request.POST.get("motivo", "").strip()
    try:
        cambiar_rol_usuario(
            actor=request.user, objetivo=objetivo, nuevo_rol=nuevo_rol, motivo=motivo, request=request
        )
        messages.success(request, f"Rol de {objetivo.email} actualizado a {nuevo_rol} y sesiones revocadas.")
    except (ValidationError, PermissionDenied) as exc:
        messages.error(request, str(exc))
    return redirect("superadmin:panel")


@solo_superadmin
@require_POST
def accion_cerrar_sesiones(request, usuario_id):
    """Cierra forzadamente todas las sesiones activas de un usuario."""
    objetivo = get_object_or_404(Usuario, pk=usuario_id)
    cerradas = cerrar_sesiones_usuario(objetivo)
    registrar_auditoria(
        usuario=request.user,
        accion=RegistroAuditoria.Accion.MODIFICAR,
        modelo="Sesion",
        objeto_id=str(objetivo.pk),
        valores_nuevos={"sesiones_cerradas": cerradas},
        motivo="Cierre forzado de sesiones desde Panel Superadmin",
        request=request,
    )
    messages.success(request, f"Se cerraron {cerradas} sesión(es) activa(s) de {objetivo.email}.")
    return redirect("superadmin:panel")


@solo_superadmin
@require_POST
def accion_kill_switch(request):
    """Activa o desactiva el interruptor general de publicaciones (requiere elevación activa)."""
    activo = request.POST.get("activo") == "1"
    motivo = request.POST.get("motivo", "").strip()
    try:
        configurar_kill_switch(actor=request.user, activo=activo, motivo=motivo)
        estado_txt = "ACTIVADO" if activo else "DESACTIVADO"
        messages.success(request, f"Interruptor general de publicaciones {estado_txt}.")
    except (ValidationError, PermissionDenied) as exc:
        messages.error(request, str(exc))
    return redirect("superadmin:panel")
