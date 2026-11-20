"""
Servicios de negocio para registro inmutable de precios, detección de duplicados,
alertas de variación atípica (> ±40 %), revisión y expiración automática (# REQ-03, 06, 09).
"""
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.mail import send_mail
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.auditoria.servicios import registrar_auditoria
from apps.nucleo.validadores import calcular_variacion_porcentual, es_variacion_atipica

from .models import AlertaPrecio, Precio


def evaluar_alertas_precio(precio: Precio) -> int:
    """
    Revisa si un precio recién publicado cumple alertas activas de vecinos y envía correo.
    Devuelve la cantidad de alertas disparadas.
    """
    if precio.estado != Precio.Estado.PUBLICADO:
        return 0
    valor = precio.precio_vigente
    candidatas = AlertaPrecio.objects.filter(
        producto=precio.producto, activa=True, precio_objetivo__gte=valor
    ).select_related("usuario")
    disparadas = 0
    for alerta in candidatas:
        if alerta.sector and alerta.sector != precio.sucursal.sector:
            continue
        send_mail(
            subject=f"[Luca PAC] ¡Bajó {precio.producto.nombre_completo} a ${valor:,}!",
            message=(
                f"Hola {alerta.usuario.nombres},\n\n"
                f"Buenas noticias: {precio.producto.nombre_completo} está a ${valor:,} en "
                f"{precio.sucursal.nombre_visible} ({precio.sucursal.direccion}, {precio.sucursal.sector}), "
                f"por debajo de tu alerta de ${alerta.precio_objetivo:,}.\n\n"
                "Equipo Luca — Cada luca cuenta."
            ),
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[alerta.usuario.email],
            fail_silently=True,
        )
        alerta.ultima_notificacion = timezone.now()
        alerta.save(update_fields=["ultima_notificacion"])
        disparadas += 1
    return disparadas


@transaction.atomic
def registrar_o_actualizar_precio(
    *,
    producto,
    sucursal,
    precio_normal: int,
    registrado_por,
    fuente: str = Precio.Fuente.COMERCIANTE,
    precio_oferta: int | None = None,
    vigencia_desde=None,
    vigencia_hasta=None,
    compra_minima: int | None = None,
    medio_pago: str = "",
    requiere_membresia: bool = False,
    nombre_membresia: str = "",
    condiciones: str = "",
    fuente_detalle: str = "",
    stock_confirmado: bool = False,
    request=None,
) -> Precio:
    """
    Crea un nuevo registro inmutable de `Precio` (# REQ-03, REQ-06, REQ-09):
    1. Valida coherencia de oferta y vigencia.
    2. Detecta duplicados con vigencia solapada y mismo valor.
    3. Calcula variación respecto al último precio publicado; si supera ±40 % activa
       `alerta_variacion` y fuerza revisión manual (`PENDIENTE`).
    4. Si se publica de inmediato (fiscalizador/admin o comercio confiable sin alerta),
       marca el registro anterior como `REEMPLAZADO` enlazándolo por `reemplaza`.
    """
    hoy = timezone.localdate()
    vig_desde = vigencia_desde or hoy
    if precio_oferta is not None and precio_oferta >= precio_normal:
        raise ValidationError("El precio de oferta debe ser menor que el precio normal.")
    if vigencia_hasta is not None and vigencia_hasta < vig_desde:
        raise ValidationError("La fecha de término de vigencia no puede ser anterior a la fecha de inicio.")

    # Detección de duplicados activos con misma vigencia y mismo valor (# REQ-09)
    duplicado = Precio.objects.filter(
        producto=producto,
        sucursal=sucursal,
        precio_normal=precio_normal,
        precio_oferta=precio_oferta,
        estado__in=[Precio.Estado.PUBLICADO, Precio.Estado.PENDIENTE],
    ).filter(
        Q(vigencia_hasta__isnull=True) | Q(vigencia_hasta__gte=vig_desde)
    )
    if duplicado.exists():
        raise ValidationError(
            "Ya existe un precio idéntico vigente o en revisión para este producto en la misma sucursal."
        )

    anterior = (
        Precio.objects.filter(producto=producto, sucursal=sucursal, estado=Precio.Estado.PUBLICADO)
        .order_by("-fecha_observacion", "-creado_en")
        .first()
    )

    alerta = False
    variacion = None
    if anterior:
        valor_nuevo = precio_oferta or precio_normal
        valor_ant = anterior.precio_vigente
        variacion = Decimal(str(calcular_variacion_porcentual(valor_ant, valor_nuevo)))
        alerta = es_variacion_atipica(valor_ant, valor_nuevo, umbral=40.0)

    es_staff = bool(registrado_por and getattr(registrado_por, "es_staff_observatorio", False))
    publicar_directo = (es_staff or sucursal.comercio.comercio_confiable) and not alerta
    estado_inicial = Precio.Estado.PUBLICADO if publicar_directo else Precio.Estado.PENDIENTE

    nuevo = Precio.objects.create(
        producto=producto,
        sucursal=sucursal,
        precio_normal=precio_normal,
        precio_oferta=precio_oferta,
        vigencia_desde=vig_desde,
        vigencia_hasta=vigencia_hasta,
        compra_minima=compra_minima,
        medio_pago=medio_pago,
        requiere_membresia=requiere_membresia,
        nombre_membresia=nombre_membresia,
        condiciones=condiciones,
        fuente=fuente,
        fuente_detalle=fuente_detalle,
        fecha_observacion=hoy,
        stock_confirmado=stock_confirmado,
        estado=estado_inicial,
        registrado_por=registrado_por,
        revisado_por=registrado_por if publicar_directo else None,
        fecha_revision=timezone.now() if publicar_directo else None,
        alerta_variacion=alerta,
        variacion_porcentual=variacion,
        reemplaza=anterior,
    )

    # Si se publica inmediatamente, el anterior pasa a REEMPLAZADO sin borrarlo (# REQ-06)
    if publicar_directo and anterior:
        anterior.estado = Precio.Estado.REEMPLAZADO
        anterior.save(update_fields=["estado", "actualizado_en"])

    if publicar_directo:
        evaluar_alertas_precio(nuevo)

    registrar_auditoria(
        usuario=registrado_por,
        accion="CREAR",
        modelo="Precio",
        objeto_id=str(nuevo.pk),
        valores_anteriores={"precio_vigente": anterior.precio_vigente} if anterior else {},
        valores_nuevos={
            "producto": producto.nombre_completo,
            "sucursal": sucursal.nombre_visible,
            "precio_normal": precio_normal,
            "precio_oferta": precio_oferta,
            "estado": estado_inicial,
            "alerta_variacion": alerta,
        },
        request=request,
    )
    return nuevo


@transaction.atomic
def aprobar_precio(precio: Precio, revisor, request=None) -> Precio:
    """Aprueba un precio pendiente y marca como REEMPLAZADO el precio publicado anterior."""
    estado_prev = precio.estado
    anterior = (
        Precio.objects.filter(
            producto=precio.producto,
            sucursal=precio.sucursal,
            estado=Precio.Estado.PUBLICADO,
        )
        .exclude(pk=precio.pk)
        .first()
    )
    if anterior:
        anterior.estado = Precio.Estado.REEMPLAZADO
        anterior.save(update_fields=["estado", "actualizado_en"])
        precio.reemplaza = anterior

    precio.estado = Precio.Estado.PUBLICADO
    precio.revisado_por = revisor
    precio.fecha_revision = timezone.now()
    precio.motivo_rechazo = ""
    precio.save(update_fields=["estado", "revisado_por", "fecha_revision", "motivo_rechazo", "reemplaza", "actualizado_en"])
    evaluar_alertas_precio(precio)

    registrar_auditoria(
        usuario=revisor,
        accion="APROBAR",
        modelo="Precio",
        objeto_id=str(precio.pk),
        valores_anteriores={"estado": estado_prev},
        valores_nuevos={"estado": precio.estado, "precio_vigente": precio.precio_vigente},
        request=request,
    )
    return precio


@transaction.atomic
def rechazar_precio(precio: Precio, revisor, motivo: str, request=None) -> Precio:
    """Rechaza un precio pendiente con motivo obligatorio (# REQ-09)."""
    if not motivo or not motivo.strip():
        raise ValidationError("Debes indicar un motivo claro de rechazo.")
    estado_prev = precio.estado
    precio.estado = Precio.Estado.RECHAZADO
    precio.revisado_por = revisor
    precio.fecha_revision = timezone.now()
    precio.motivo_rechazo = motivo.strip()
    precio.save(update_fields=["estado", "revisado_por", "fecha_revision", "motivo_rechazo", "actualizado_en"])

    registrar_auditoria(
        usuario=revisor,
        accion="RECHAZAR",
        modelo="Precio",
        objeto_id=str(precio.pk),
        valores_anteriores={"estado": estado_prev},
        valores_nuevos={"estado": precio.estado, "motivo": precio.motivo_rechazo},
        request=request,
    )
    return precio


def expirar_ofertas_vencidas(usuario=None, request=None) -> int:
    """Marca como VENCIDO todo precio/oferta publicado cuya `vigencia_hasta` ya pasó (# REQ-09)."""
    hoy = timezone.localdate()
    vencidos = Precio.objects.filter(
        estado=Precio.Estado.PUBLICADO,
        vigencia_hasta__isnull=False,
        vigencia_hasta__lt=hoy,
    )
    cantidad = vencidos.update(estado=Precio.Estado.VENCIDO)
    if cantidad > 0:
        registrar_auditoria(
            usuario=usuario,
            accion="MODIFICAR",
            modelo="Precio",
            objeto_id="lote_vencimiento",
            valores_nuevos={"ofertas_expiradas": cantidad, "fecha": str(hoy)},
            request=request,
        )
    return cantidad
