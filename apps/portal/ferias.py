"""
Utilidades para detectar qué Ferias Libres y Mercados de Pedro Aguirre Cerda
funcionan HOY y su calendario semanal (# Funcionalidad Ferias abiertas HOY).
"""
from django.utils import timezone

from apps.comercios.models import Sucursal

DIAS_SEMANA = [
    (0, "Lunes", "lun"),
    (1, "Martes", "mar"),
    (2, "Miércoles", "mié"),
    (3, "Jueves", "jue"),
    (4, "Viernes", "vie"),
    (5, "Sábado", "sáb"),
    (6, "Domingo", "dom"),
]


def _dias_activos_desde_horario(horario: str) -> set[int]:
    """Interpreta cadenas de horario chilenas como 'Mié y Sáb 08:00–15:30' o 'Lun a Sáb'."""
    h = (horario or "").lower()
    if "lun a dom" in h:
        return {0, 1, 2, 3, 4, 5, 6}
    if "lun a sáb" in h or "lun a sab" in h:
        return {0, 1, 2, 3, 4, 5}
    if "lun a vie" in h:
        return {0, 1, 2, 3, 4}

    dias = set()
    mapa = {
        "lun": 0,
        "mar": 1,
        "mié": 2,
        "mie": 2,
        "jue": 3,
        "vie": 4,
        "sáb": 5,
        "sab": 5,
        "dom": 6,
    }
    for token, idx in mapa.items():
        if token in h:
            dias.add(idx)
    return dias


def obtener_ferias_por_dia(dia_semana: int | None = None) -> dict:
    """Devuelve las ferias abiertas hoy (o en `dia_semana`) y el listado semanal completo."""
    hoy_idx = timezone.localdate().weekday() if dia_semana is None else int(dia_semana) % 7
    nombre_dia = DIAS_SEMANA[hoy_idx][1]

    ferias = list(
        Sucursal.objects.filter(
            activa=True, comercio__activo=True, comercio__estado="ACTIVO", comercio__tipo="FERIA"
        ).select_related("comercio")
    )

    abiertas_hoy = []
    calendario = []
    for f in ferias:
        dias = _dias_activos_desde_horario(f.horario)
        abre_hoy = hoy_idx in dias
        item = {
            "sucursal": f,
            "abre_hoy": abre_hoy,
            "dias_nombres": [DIAS_SEMANA[d][1] for d in sorted(dias)],
        }
        calendario.append(item)
        if abre_hoy:
            abiertas_hoy.append(item)

    return {
        "dia_actual_idx": hoy_idx,
        "dia_actual_nombre": nombre_dia,
        "abiertas_hoy": abiertas_hoy,
        "todas": calendario,
        "dias_semana": DIAS_SEMANA,
    }
