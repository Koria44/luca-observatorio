"""Servicio centralizado para escribir eventos de auditoría y verificar su cadena de integridad (# REQ-15 / Prompt 7)."""
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
    motivo: str = "",
    request=None,
) -> RegistroAuditoria:
    """Inserta un nuevo evento en la bitácora inmutable de auditoría con hash encadenado."""
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
        motivo=motivo,
        ip=ip,
        user_agent=ua,
    )


def verificar_integridad_auditoria(limite: int = 500) -> dict:
    """
    Recorre los registros de auditoría con hash encadenado y verifica que ninguno haya sido alterado (# Sección 8).
    Nota de limitación: detecta alteraciones posteriores en la BD local, pero no reemplaza respaldos WORM externos.
    """
    registros = list(RegistroAuditoria.objects.exclude(hash_actual="").order_by("id")[:limite])
    alterados = []
    esperado_prev = None
    for reg in registros:
        if esperado_prev is not None and reg.hash_anterior != esperado_prev:
            alterados.append(reg.id)
        if reg.hash_actual != reg.calcular_hash():
            alterados.append(reg.id)
        esperado_prev = reg.hash_actual
    return {
        "verificados": len(registros),
        "integro": len(alterados) == 0,
        "registros_alterados": sorted(set(alterados)),
    }
