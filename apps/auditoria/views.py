"""Vistas estrictamente exclusivas de SUPERADMIN para consulta, integridad y exportación de auditoría (# REQ-15 / Prompt 8)."""
import csv

from django.conf import settings
from django.core.mail import send_mail
from django.http import HttpResponse
from django.shortcuts import render

from apps.nucleo.permisos import solo_superadmin

from .models import RegistroAuditoria
from .servicios import registrar_auditoria, verificar_integridad_auditoria


def _sanitizar_celda_csv(valor) -> str:
    """Escapa fórmulas peligrosas (=, +, -, @) en exportaciones CSV (# SEGURIDAD / II.11)."""
    texto = str(valor if valor is not None else "")
    if texto and texto[0] in ("=", "+", "-", "@"):
        return f"'{texto}"
    return texto


@solo_superadmin
def lista_auditoria(request):
    """
    Consulta filtrable, verificación de integridad SHA-256 y exportación CSV del registro
    de auditoría. EXCLUSIVO para SUPERADMIN; cualquier otro rol o anónimo recibe 404.
    """
    registros = RegistroAuditoria.objects.select_related("usuario")
    accion = request.GET.get("accion", "").strip()
    modelo = request.GET.get("modelo", "").strip()
    usuario_q = request.GET.get("usuario", "").strip()
    fecha_desde = request.GET.get("desde", "").strip()

    if accion:
        registros = registros.filter(accion=accion)
    if modelo:
        registros = registros.filter(modelo__icontains=modelo)
    if usuario_q:
        registros = registros.filter(usuario__email__icontains=usuario_q)
    if fecha_desde:
        registros = registros.filter(fecha__date__gte=fecha_desde)

    integridad = None
    if request.GET.get("verificar") == "1":
        integridad = verificar_integridad_auditoria()
        registrar_auditoria(
            usuario=request.user,
            accion=RegistroAuditoria.Accion.MODIFICAR,
            modelo="RegistroAuditoria",
            valores_nuevos={"verificacion_integridad": integridad},
            motivo="Verificación manual de integridad SHA-256 por SUPERADMIN",
            request=request,
        )

    if request.GET.get("exportar") == "csv":
        registrar_auditoria(
            usuario=request.user,
            accion=RegistroAuditoria.Accion.EXPORTAR,
            modelo="RegistroAuditoria",
            valores_nuevos={"formato": "csv", "filtros": dict(request.GET)},
            motivo="Exportación de auditoría por SUPERADMIN",
            request=request,
        )
        correo_ctrl = getattr(settings, "SUPERADMIN_CORREO_CONTROL", "")
        if correo_ctrl:
            send_mail(
                subject="[Luca · Control] Exportación de Registro de Auditoría",
                message=(
                    f"El superadministrador {request.user.email} exportó el registro de auditoría en CSV.\n"
                    f"Filtros aplicados: {dict(request.GET)}\n"
                ),
                from_email=getattr(settings, "DEFAULT_FROM_EMAIL", "noreply@luca-pac.cl"),
                recipient_list=[correo_ctrl],
                fail_silently=True,
            )
        resp = HttpResponse(content_type="text/csv; charset=utf-8")
        resp["Content-Disposition"] = 'attachment; filename="auditoria_luca.csv"'
        resp.write("\ufeff")  # BOM UTF-8 para Excel
        writer = csv.writer(resp)
        writer.writerow(["Fecha", "Usuario", "Acción", "Modelo", "Objeto ID", "IP", "Motivo", "Valores anteriores", "Valores nuevos"])
        for r in registros[:2000]:
            writer.writerow([
                _sanitizar_celda_csv(r.fecha.strftime("%Y-%m-%d %H:%M:%S")),
                _sanitizar_celda_csv(r.usuario.email if r.usuario else "Sistema"),
                _sanitizar_celda_csv(r.accion),
                _sanitizar_celda_csv(r.modelo),
                _sanitizar_celda_csv(r.objeto_id),
                _sanitizar_celda_csv(r.ip or ""),
                _sanitizar_celda_csv(r.motivo or ""),
                _sanitizar_celda_csv(r.valores_anteriores),
                _sanitizar_celda_csv(r.valores_nuevos),
            ])
        return resp

    return render(
        request,
        "auditoria/lista.html",
        {
            "registros": registros[:200],
            "acciones": RegistroAuditoria.Accion.choices,
            "filtros": {"accion": accion, "modelo": modelo, "usuario": usuario_q, "desde": fecha_desde},
            "integridad": integridad,
        },
    )
