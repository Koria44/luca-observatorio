"""Vistas restringidas de consulta y exportación de auditoría (# REQ-15)."""
import csv

from django.http import HttpResponse
from django.shortcuts import render

from apps.nucleo.permisos import solo_fiscalizador_o_admin

from .models import RegistroAuditoria
from .servicios import registrar_auditoria


def _sanitizar_celda_csv(valor) -> str:
    """Escapa fórmulas peligrosas (=, +, -, @) en exportaciones CSV (# SEGURIDAD / II.11)."""
    texto = str(valor if valor is not None else "")
    if texto and texto[0] in ("=", "+", "-", "@"):
        return f"'{texto}"
    return texto


@solo_fiscalizador_o_admin
def lista_auditoria(request):
    """Consulta filtrable del registro de auditoría (solo lectura para fiscalizador y admin)."""
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

    if request.GET.get("exportar") == "csv":
        registrar_auditoria(
            usuario=request.user,
            accion=RegistroAuditoria.Accion.EXPORTAR,
            modelo="RegistroAuditoria",
            valores_nuevos={"formato": "csv", "filtros": dict(request.GET)},
            request=request,
        )
        resp = HttpResponse(content_type="text/csv; charset=utf-8")
        resp["Content-Disposition"] = 'attachment; filename="auditoria_luca.csv"'
        resp.write("\ufeff")  # BOM UTF-8 para Excel
        writer = csv.writer(resp)
        writer.writerow(["Fecha", "Usuario", "Acción", "Modelo", "Objeto ID", "IP", "Valores anteriores", "Valores nuevos"])
        for r in registros[:2000]:
            writer.writerow([
                _sanitizar_celda_csv(r.fecha.strftime("%Y-%m-%d %H:%M:%S")),
                _sanitizar_celda_csv(r.usuario.email if r.usuario else "Sistema"),
                _sanitizar_celda_csv(r.accion),
                _sanitizar_celda_csv(r.modelo),
                _sanitizar_celda_csv(r.objeto_id),
                _sanitizar_celda_csv(r.ip or ""),
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
        },
    )
