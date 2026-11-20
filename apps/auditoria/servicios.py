"""Servicio centralizado para escribir eventos de auditoría (# REQ-15)."""
from apps.nucleo.middleware import obtener_ip_cliente

from .models import RegistroAuditoria


def registrar_auditoria(
    *,
    usuario=None,
    accion: str,
    modelo: str,
    objeto_id: str = "",
    valores_anteriores: dict | None = None,
    valores_nuevos: dict | None = None,
    request=None,
) -> RegistroAuditoria:
    """Inserta un nuevo evento en la bitácora inmutable de auditoría."""
    ip = obtener_ip_cliente(request) if request is not None else None
    ua = request.META.get("HTTP_USER_AGENT", "")[:255] if request is not None else ""
    usuario_real = usuario if (usuario and getattr(usuario, "is_authenticated", True)) else None
    return RegistroAuditoria.objects.create(
        usuario=usuario_real,
        accion=accion,
        modelo=modelo,
        objeto_id=str(objeto_id),
        valores_anteriores=valores_anteriores or {},
        valores_nuevos=valores_nuevos or {},
        ip=ip,
        user_agent=ua,
    )
