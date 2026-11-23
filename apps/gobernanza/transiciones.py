"""
Máquinas de estados formales y servicios únicos de transición (# Prompt 7 Sección 3).

PROHIBIDO mutar `estado` directamente en vistas (`obj.estado = X; obj.save()`).
Toda transición pasa por este módulo: valida transición permitida, permiso en `politicas.puede()`,
separación de funciones ("cuatro ojos"), ejecuta en `transaction.atomic()` con `select_for_update()`,
registra auditoría con motivo y crea notificación para el usuario afectado.
"""
from django.conf import settings
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.mail import send_mail
from django.db import transaction
from django.utils import timezone

from apps.auditoria.models import RegistroAuditoria
from apps.auditoria.servicios import registrar_auditoria
from apps.nucleo.middleware import cerrar_sesiones_usuario
from apps.nucleo.politicas import (
    es_administrador,
    es_staff_activo,
    es_superadmin,
    puede,
    puede_gestionar_usuario,
)
from apps.nucleo.totp import verificar_codigo_totp
from apps.precios.models import Precio

from .models import (
    Apelacion,
    ConfiguracionObservatorio,
    ElevacionSuperadmin,
    Habilitacion,
    HistorialEstado,
    HistorialHabilitacion,
    Notificacion,
    Sancion,
    SolicitudProducto,
)

# Tablas declarativas de transiciones válidas (# Sección 3)
TRANSICIONES_HABILITACION = {
    Habilitacion.Estado.SOLICITADA: {Habilitacion.Estado.EN_REVISION, Habilitacion.Estado.RECHAZADA},
    Habilitacion.Estado.EN_REVISION: {
        Habilitacion.Estado.OBSERVADA,
        Habilitacion.Estado.OTORGADA,
        Habilitacion.Estado.RECHAZADA,
    },
    Habilitacion.Estado.OBSERVADA: {Habilitacion.Estado.EN_REVISION, Habilitacion.Estado.RECHAZADA},
    Habilitacion.Estado.OTORGADA: {
        Habilitacion.Estado.SUSPENDIDA,
        Habilitacion.Estado.REVOCADA,
        Habilitacion.Estado.VENCIDA,
    },
    Habilitacion.Estado.SUSPENDIDA: {Habilitacion.Estado.OTORGADA, Habilitacion.Estado.REVOCADA},
    Habilitacion.Estado.VENCIDA: {Habilitacion.Estado.EN_REVISION, Habilitacion.Estado.OTORGADA},
    Habilitacion.Estado.RECHAZADA: set(),
    Habilitacion.Estado.REVOCADA: set(),
}

TRANSICIONES_PRECIO = {
    Precio.Estado.BORRADOR: {Precio.Estado.PENDIENTE},
    Precio.Estado.PENDIENTE: {Precio.Estado.OBSERVADO, Precio.Estado.PUBLICADO, Precio.Estado.RECHAZADO},
    Precio.Estado.OBSERVADO: {Precio.Estado.PENDIENTE, Precio.Estado.RECHAZADO},
    Precio.Estado.PUBLICADO: {
        Precio.Estado.REEMPLAZADO,
        Precio.Estado.VENCIDO,
        Precio.Estado.OCULTO,
        Precio.Estado.RETIRADO,
    },
    Precio.Estado.RECHAZADO: set(),
    Precio.Estado.REEMPLAZADO: set(),
    Precio.Estado.VENCIDO: set(),
    Precio.Estado.OCULTO: {Precio.Estado.PUBLICADO, Precio.Estado.RETIRADO},
    Precio.Estado.RETIRADO: set(),
}

MOTIVOS_RECHAZO_CATALOGO = [
    ("FUERA_RANGO", "Precio fuera del rango plausible de mercado"),
    ("EVIDENCIA_INSUFICIENTE", "Falta evidencia o boleta legible"),
    ("OFERTA_INCONSISTENTE", "Condiciones o descuento de oferta inconsistentes"),
    ("CATEGORIA_NO_AUTORIZADA", "Categoría fuera del alcance de habilitación"),
    ("POSIBLE_CEBO", "Sospecha de precio cebo o discrepancia en terreno"),
    ("OTRO", "Otro motivo especificado"),
]


def _notificar(usuario, titulo: str, mensaje: str, enlace: str = "") -> None:
    if usuario is not None:
        Notificacion.objects.create(usuario=usuario, titulo=titulo[:160], mensaje=mensaje, enlace=enlace[:255])


def _auditar(usuario, accion: str, modelo: str, obj_id, ant: dict, nvo: dict, motivo: str = "") -> None:
    RegistroAuditoria.objects.create(
        usuario=usuario,
        accion=accion,
        modelo=modelo,
        objeto_id=str(obj_id),
        valores_anteriores=ant,
        valores_nuevos=nvo,
        motivo=motivo,
    )


def _registrar_historial_estado(modelo: str, obj_id, origen: str, destino: str, actor, motivo: str = "") -> None:
    """Escribe línea de tiempo funcional SIN IP, user-agent ni detalles internos (# Prompt 8 Sección 3.2)."""
    nombre = actor.nombre_completo if (actor and hasattr(actor, "nombre_completo")) else "Sistema"
    cargo = actor.get_rol_display() if (actor and hasattr(actor, "get_rol_display")) else ""
    HistorialEstado.objects.create(
        modelo=modelo,
        objeto_id=str(obj_id),
        estado_anterior=origen,
        estado_nuevo=destino,
        resuelto_por_nombre=nombre[:120],
        resuelto_por_cargo=cargo[:60],
        motivo=motivo,
    )


@transaction.atomic
def transicionar_habilitacion(
    *,
    habilitacion_id: int,
    estado_destino: str,
    actor,
    motivo: str = "",
    nivel: int | None = None,
    vigente_hasta=None,
) -> Habilitacion:
    """Única vía autorizada para transitar una Habilitación (# Sección 2 y 3)."""
    hab = Habilitacion.objects.select_for_update().select_related("comercio", "comercio__propietario").get(pk=habilitacion_id)
    origen = hab.estado
    permitidos = TRANSICIONES_HABILITACION.get(origen, set())
    if estado_destino not in permitidos:
        raise ValidationError(f"Transición de habilitación no permitida: {origen} -> {estado_destino}.")

    # Verificar permisos y cuatro ojos según destino
    if estado_destino == Habilitacion.Estado.OTORGADA:
        if not puede(actor, "otorgar_habilitacion", hab):
            _auditar(actor, RegistroAuditoria.Accion.DENEGADO, "Habilitacion", hab.pk, {"estado": origen}, {"intento": estado_destino}, "Sin permiso o violación cuatro ojos")
            raise PermissionDenied("Solo un administrador distinto del solicitante puede otorgar la habilitación.")
        if not hab.checklist.get("datos_coinciden") and not es_administrador(actor):
            raise ValidationError("Debe completar la lista de verificación antes de aprobar.")
    elif estado_destino in (Habilitacion.Estado.SUSPENDIDA, Habilitacion.Estado.REVOCADA):
        if not puede(actor, "revocar_habilitacion", hab):
            raise PermissionDenied("Solo un administrador puede suspender o revocar habilitaciones.")
        if not motivo.strip():
            raise ValidationError("Debe indicar un motivo obligatorio para suspender o revocar.")
    elif estado_destino in (Habilitacion.Estado.EN_REVISION, Habilitacion.Estado.OBSERVADA, Habilitacion.Estado.RECHAZADA):
        # Si el comercio reenvía desde OBSERVADA -> EN_REVISION se permite al propietario
        if not (origen == Habilitacion.Estado.OBSERVADA and estado_destino == Habilitacion.Estado.EN_REVISION):
            if not puede(actor, "revisar_habilitacion", hab):
                raise PermissionDenied("No tienes permiso para revisar esta habilitación.")
            if estado_destino in (Habilitacion.Estado.OBSERVADA, Habilitacion.Estado.RECHAZADA) and not motivo.strip():
                raise ValidationError("Debes ingresar observaciones o motivo de rechazo.")

    nivel_ant = hab.nivel
    hab.estado = estado_destino
    if estado_destino == Habilitacion.Estado.OTORGADA:
        hab.nivel = nivel if nivel in (1, 2) else max(1, hab.nivel)
        hab.otorgada_por = actor
        hab.fecha_otorgamiento = timezone.now()
        hab.vigente_hasta = vigente_hasta or (timezone.localdate() + timezone.timedelta(days=365))
        hab.motivo = motivo or "Habilitación otorgada"
    elif estado_destino in (Habilitacion.Estado.SUSPENDIDA, Habilitacion.Estado.REVOCADA):
        hab.revocada_por = actor
        hab.fecha_revocacion = timezone.now()
        hab.motivo_revocacion = motivo
        if estado_destino == Habilitacion.Estado.REVOCADA:
            hab.nivel = Habilitacion.Nivel.SIN_HABILITACION
        # Ocultar precios vigentes del comercio al suspender/revocar (# Sección 2.6)
        Precio.objects.filter(sucursal__comercio=hab.comercio, estado=Precio.Estado.PUBLICADO).update(
            estado=Precio.Estado.OCULTO
        )
    elif estado_destino == Habilitacion.Estado.OBSERVADA:
        hab.revisada_por = actor
        hab.observaciones = motivo
    elif estado_destino == Habilitacion.Estado.RECHAZADA:
        hab.revisada_por = actor
        hab.motivo = motivo

    hab.save()

    HistorialHabilitacion.objects.create(
        habilitacion=hab,
        estado_anterior=origen,
        estado_nuevo=estado_destino,
        nivel_anterior=nivel_ant,
        nivel_nuevo=hab.nivel,
        actor=actor,
        motivo=motivo,
    )
    _registrar_historial_estado("Habilitacion", hab.pk, origen, estado_destino, actor, motivo=motivo)
    _auditar(
        actor,
        RegistroAuditoria.Accion.HABILITACION,
        "Habilitacion",
        hab.pk,
        {"estado": origen, "nivel": nivel_ant},
        {"estado": estado_destino, "nivel": hab.nivel},
        motivo=motivo,
    )
    _notificar(
        hab.comercio.propietario,
        f"Tu habilitación pasó a {hab.get_estado_display()}",
        motivo or f"Comercio {hab.comercio.nombre_fantasia}: nuevo estado {hab.get_estado_display()}.",
        "/panel/comerciante/",
    )
    return hab


@transaction.atomic
def transicionar_precio(
    *,
    precio_id: int,
    estado_destino: str,
    actor,
    motivo: str = "",
) -> Precio:
    """Única vía autorizada para aprobar, observar, rechazar u ocultar un Precio (# Sección 3)."""
    precio = Precio.objects.select_for_update().select_related("sucursal", "sucursal__comercio", "producto").get(pk=precio_id)
    origen = precio.estado
    if estado_destino not in TRANSICIONES_PRECIO.get(origen, set()):
        raise ValidationError(f"Transición de precio no permitida: {origen} -> {estado_destino}.")

    if not puede(actor, "revisar_precio", precio):
        _auditar(actor, RegistroAuditoria.Accion.DENEGADO, "Precio", precio.pk, {"estado": origen}, {"intento": estado_destino}, "Sin permiso o cuatro ojos")
        raise PermissionDenied("No puedes revisar este precio (requiere rol municipal y ser distinto del autor).")

    if estado_destino in (Precio.Estado.RECHAZADO, Precio.Estado.OBSERVADO, Precio.Estado.OCULTO) and not motivo.strip():
        raise ValidationError("Debes indicar un motivo estandarizado o comentario.")

    precio.estado = estado_destino
    precio.revisado_por = actor
    precio.fecha_revision = timezone.now()
    if estado_destino == Precio.Estado.PUBLICADO:
        precio.regla_publicacion = Precio.ReglaPublicacion.APROBACION_MANUAL
        # Reemplazar precio publicado anterior del mismo producto/sucursal
        Precio.objects.filter(
            producto=precio.producto,
            sucursal=precio.sucursal,
            estado=Precio.Estado.PUBLICADO,
        ).exclude(pk=precio.pk).update(estado=Precio.Estado.REEMPLAZADO)
    elif estado_destino in (Precio.Estado.RECHAZADO, Precio.Estado.OBSERVADO):
        precio.motivo_rechazo = motivo

    precio.save(update_fields=["estado", "revisado_por", "fecha_revision", "regla_publicacion", "motivo_rechazo", "actualizado_en"])

    accion_aud = (
        RegistroAuditoria.Accion.APROBAR
        if estado_destino == Precio.Estado.PUBLICADO
        else RegistroAuditoria.Accion.RECHAZAR
        if estado_destino == Precio.Estado.RECHAZADO
        else RegistroAuditoria.Accion.MODIFICAR
    )
    _auditar(actor, accion_aud, "Precio", precio.pk, {"estado": origen}, {"estado": estado_destino}, motivo=motivo)
    _registrar_historial_estado("Precio", precio.pk, origen, estado_destino, actor, motivo=motivo)
    _notificar(
        precio.registrado_por,
        f"Precio {precio.get_estado_display()}: {precio.producto.nombre}",
        motivo or f"Tu precio en {precio.sucursal.nombre_visible} pasó a {precio.get_estado_display()}.",
        "/precios/mis-precios/",
    )
    return precio


@transaction.atomic
def tomar_caso_precio(precio_id: int, actor, minutos: int = 20) -> Precio:
    """Bloqueo temporal para evitar que dos revisores trabajen simultáneamente el mismo precio (# Sección 3)."""
    if not es_staff_activo(actor):
        raise PermissionDenied("Solo personal municipal puede tomar casos de revisión.")
    precio = Precio.objects.select_for_update().get(pk=precio_id)
    ahora = timezone.now()
    if precio.tomado_por_id and precio.tomado_por_id != actor.id and precio.tomado_hasta and precio.tomado_hasta > ahora:
        raise ValidationError("Este caso ya está siendo revisado por otro fiscalizador.")
    precio.tomado_por = actor
    precio.tomado_hasta = ahora + timezone.timedelta(minutes=minutos)
    precio.save(update_fields=["tomado_por", "tomado_hasta"])
    return precio


@transaction.atomic
def aplicar_sancion_comercio(
    *,
    comercio,
    tipo: str,
    motivo: str,
    evidencia: str,
    actor,
    dias_suspension: int | None = None,
) -> Sancion:
    """Aplica medida gradual (Advertencia -> Suspensión -> Revocación) con efecto en habilitación y precios (# Sección 2.6)."""
    if not puede(actor, "aplicar_sancion", comercio):
        raise PermissionDenied("Solo un administrador puede aplicar sanciones.")
    if not motivo.strip():
        raise ValidationError("Toda sanción requiere motivo documentado.")

    termino = timezone.localdate() + timezone.timedelta(days=dias_suspension) if dias_suspension else None
    sancion = Sancion.objects.create(
        comercio=comercio,
        tipo=tipo,
        motivo=motivo,
        evidencia=evidencia,
        aplicada_por=actor,
        fecha_termino=termino,
        activa=True,
    )

    hab = Habilitacion.objects.filter(comercio=comercio, estado=Habilitacion.Estado.OTORGADA).first()
    if hab:
        if tipo == Sancion.Tipo.ADVERTENCIA and hab.nivel == Habilitacion.Nivel.CONFIABLE:
            # Degradación automática Nivel 2 -> Nivel 1 ante discrepancia grave (# Sección 2.2)
            hab.nivel = Habilitacion.Nivel.SUPERVISADO
            hab.save(update_fields=["nivel", "actualizado_en"])
            HistorialHabilitacion.objects.create(
                habilitacion=hab,
                estado_anterior=hab.estado,
                estado_nuevo=hab.estado,
                nivel_anterior=2,
                nivel_nuevo=1,
                actor=actor,
                motivo=f"Degradación automática por advertencia: {motivo}",
            )
        elif tipo == Sancion.Tipo.SUSPENSION_TEMPORAL:
            transicionar_habilitacion(
                habilitacion_id=hab.pk,
                estado_destino=Habilitacion.Estado.SUSPENDIDA,
                actor=actor,
                motivo=motivo,
            )
        elif tipo == Sancion.Tipo.REVOCACION:
            transicionar_habilitacion(
                habilitacion_id=hab.pk,
                estado_destino=Habilitacion.Estado.REVOCADA,
                actor=actor,
                motivo=motivo,
            )

    _auditar(actor, RegistroAuditoria.Accion.SANCION, "Comercio", comercio.pk, {}, {"tipo": tipo, "termino": str(termino)}, motivo=motivo)
    _notificar(comercio.propietario, f"Medida aplicada: {sancion.get_tipo_display()}", motivo, "/panel/comerciante/")
    return sancion


@transaction.atomic
def resolver_apelacion(*, apelacion_id: int, estado_destino: str, resolucion: str, actor) -> Apelacion:
    """Resuelve apelación aplicando separación de funciones (revisor != sancionador) (# Sección 2.6)."""
    ap = Apelacion.objects.select_for_update().select_related("sancion", "sancion__comercio").get(pk=apelacion_id)
    if ap.estado != Apelacion.Estado.PENDIENTE:
        raise ValidationError("Esta apelación ya fue resuelta.")
    if not puede(actor, "resolver_apelacion", ap):
        raise PermissionDenied("Debe resolver un funcionario distinto al que aplicó la sanción.")
    if estado_destino not in (Apelacion.Estado.ACOGIDA, Apelacion.Estado.RECHAZADA):
        raise ValidationError("Estado de resolución inválido.")
    if not resolucion.strip():
        raise ValidationError("Debe explicar el fundamento de la resolución.")

    ap.estado = estado_destino
    ap.resuelta_por = actor
    ap.resolucion = resolucion
    ap.fecha_resolucion = timezone.now()
    ap.save()

    if estado_destino == Apelacion.Estado.ACOGIDA:
        ap.sancion.activa = False
        ap.sancion.save(update_fields=["activa"])
        hab = Habilitacion.objects.filter(
            comercio=ap.sancion.comercio, estado=Habilitacion.Estado.SUSPENDIDA
        ).first()
        if hab and es_administrador(actor):
            transicionar_habilitacion(
                habilitacion_id=hab.pk,
                estado_destino=Habilitacion.Estado.OTORGADA,
                actor=actor,
                motivo=f"Apelación acogida: {resolucion}",
                nivel=Habilitacion.Nivel.SUPERVISADO,
            )

    _auditar(actor, RegistroAuditoria.Accion.MODIFICAR, "Apelacion", ap.pk, {"estado": "PENDIENTE"}, {"estado": estado_destino}, motivo=resolucion)
    return ap


@transaction.atomic
def configurar_kill_switch(*, actor, activo: bool, motivo: str, comercio_id: int | None = None) -> ConfiguracionObservatorio:
    """Interruptor general o por comercio para pausar publicaciones nuevas (# Sección 2.7)."""
    if not puede(actor, "gestionar_kill_switch"):
        raise PermissionDenied("Solo un administrador puede accionar el interruptor general.")
    if not motivo.strip():
        raise ValidationError("Debes registrar un motivo para accionar el interruptor general.")
    cfg = ConfiguracionObservatorio.obtener()
    ant = {"kill_switch_global": cfg.kill_switch_global, "comercios_pausados": list(cfg.comercios_pausados or [])}
    if comercio_id is None:
        cfg.kill_switch_global = activo
        cfg.kill_switch_motivo = motivo
    else:
        pausados = set(cfg.comercios_pausados or [])
        if activo:
            pausados.add(int(comercio_id))
        else:
            pausados.discard(int(comercio_id))
        cfg.comercios_pausados = sorted(pausados)
    cfg.actualizado_por = actor
    cfg.save()
    _auditar(
        actor,
        RegistroAuditoria.Accion.MODIFICAR,
        "ConfiguracionObservatorio",
        cfg.pk,
        ant,
        {"kill_switch_global": cfg.kill_switch_global, "comercios_pausados": cfg.comercios_pausados},
        motivo=motivo,
    )
    return cfg


@transaction.atomic
def decidir_solicitud_producto(*, solicitud_id: int, aprobar: bool, actor, motivo: str = "") -> SolicitudProducto:
    """Revisión con cuatro ojos de una SolicitudProducto enviada por comercio (# Sección 5.6)."""
    sol = SolicitudProducto.objects.select_for_update().select_related("categoria").get(pk=solicitud_id)
    if sol.estado != SolicitudProducto.Estado.PENDIENTE:
        raise ValidationError("La solicitud ya fue resuelta.")
    if not puede(actor, "revisar_solicitud_producto", sol):
        raise PermissionDenied("No tienes permiso para revisar esta solicitud de producto.")
    if not aprobar and not motivo.strip():
        raise ValidationError("Debe indicar motivo de rechazo.")

    sol.revisado_por = actor
    sol.motivo_decision = motivo
    if aprobar:
        from apps.catalogo.models import Marca, Producto

        marca_obj, _ = Marca.objects.get_or_create(nombre=(sol.marca_texto or "Genérico Local").strip())
        prod, _ = Producto.objects.get_or_create(
            nombre=sol.nombre.strip(),
            marca=marca_obj,
            contenido=sol.contenido,
            unidad_medida=sol.unidad_medida,
            defaults={
                "categoria": sol.categoria,
                "codigo_barras": sol.codigo_barras or None,
                "activo": True,
            },
        )
        sol.producto_creado = prod
        sol.estado = SolicitudProducto.Estado.APROBADA
    else:
        sol.estado = SolicitudProducto.Estado.RECHAZADA
    sol.save()
    _auditar(actor, RegistroAuditoria.Accion.APROBAR if aprobar else RegistroAuditoria.Accion.RECHAZAR, "SolicitudProducto", sol.pk, {"estado": "PENDIENTE"}, {"estado": sol.estado}, motivo=motivo)
    return sol


@transaction.atomic
def activar_elevacion_superadmin(
    *,
    superadmin,
    motivo: str,
    codigo_totp: str = "",
    minutos: int = 30,
    request=None,
) -> ElevacionSuperadmin:
    """
    Habilita elevación temporal (máx. 30 min) para que un SUPERADMIN ejecute una acción
    operativa de negocio, exigiendo motivo, TOTP válido si está configurado, registro en
    auditoría y correo de control (# Prompt 8 Sección 1.3).
    """
    if not es_superadmin(superadmin):
        raise PermissionDenied("Solo un SUPERADMIN activo puede solicitar elevación temporal.")
    if not motivo or len(motivo.strip()) < 8:
        raise ValidationError("Debes ingresar un motivo claro (mínimo 8 caracteres) para la elevación temporal.")
    if superadmin.totp_activo:
        if not verificar_codigo_totp(superadmin.totp_secreto, codigo_totp):
            raise ValidationError("Código TOTP inválido para autorizar la elevación temporal.")

    duracion = max(1, min(int(minutos), 30))
    ahora = timezone.now()
    elev = ElevacionSuperadmin.objects.create(
        superadmin=superadmin,
        motivo=motivo.strip(),
        activa_hasta=ahora + timezone.timedelta(minutes=duracion),
    )
    registrar_auditoria(
        usuario=superadmin,
        accion=RegistroAuditoria.Accion.MODIFICAR,
        modelo="ElevacionSuperadmin",
        objeto_id=str(elev.pk),
        valores_nuevos={"activa_hasta": elev.activa_hasta.isoformat(), "minutos": duracion},
        motivo=motivo.strip(),
        request=request,
    )
    correo_ctrl = getattr(settings, "SUPERADMIN_CORREO_CONTROL", "")
    if correo_ctrl:
        send_mail(
            subject="[Luca · Control] Elevación temporal de SUPERADMIN activada",
            message=(
                f"El superadministrador {superadmin.email} activó una elevación temporal de {duracion} minutos.\n"
                f"Vigente hasta: {elev.activa_hasta.strftime('%d/%m/%Y %H:%M')}\n"
                f"Motivo: {motivo.strip()}\n"
            ),
            from_email=getattr(settings, "DEFAULT_FROM_EMAIL", "noreply@luca-pac.cl"),
            recipient_list=[correo_ctrl],
            fail_silently=True,
        )
    return elev


@transaction.atomic
def revocar_elevacion_superadmin(*, superadmin, request=None) -> int:
    """Revoca inmediatamente cualquier elevación temporal activa del SUPERADMIN."""
    if not es_superadmin(superadmin):
        raise PermissionDenied("Solo un SUPERADMIN activo puede revocar su elevación.")
    actualizadas = ElevacionSuperadmin.objects.filter(
        superadmin=superadmin, revocada=False, activa_hasta__gt=timezone.now()
    ).update(revocada=True)
    if actualizadas:
        registrar_auditoria(
            usuario=superadmin,
            accion=RegistroAuditoria.Accion.MODIFICAR,
            modelo="ElevacionSuperadmin",
            objeto_id=str(superadmin.pk),
            valores_nuevos={"revocadas": actualizadas},
            motivo="Revocación manual de elevación temporal",
            request=request,
        )
    return actualizadas


@transaction.atomic
def cambiar_rol_usuario(*, actor, objetivo, nuevo_rol: str, motivo: str = "", request=None):
    """
    Cambia el rol de un usuario respetando jerarquía, protección del último SUPERADMIN,
    invalidación inmediata de sesiones y auditoría (# Prompt 8 Sección 1.4 / 4.2).
    """
    from apps.cuentas.models import Usuario

    roles_validos = {r[0] for r in Usuario.Rol.choices}
    if nuevo_rol not in roles_validos:
        raise ValidationError("Rol destino inválido.")
    if not puede_gestionar_usuario(actor, objetivo, nuevo_rol=nuevo_rol):
        registrar_auditoria(
            usuario=actor,
            accion=RegistroAuditoria.Accion.DENEGADO,
            modelo="Usuario",
            objeto_id=str(objetivo.pk),
            valores_anteriores={"rol": objetivo.rol},
            valores_nuevos={"intento_rol": nuevo_rol},
            motivo="Violación de jerarquía o protección del último superadmin",
            request=request,
        )
        raise PermissionDenied("No tienes permiso para asignar ese rol a este usuario.")

    rol_anterior = objetivo.rol
    objetivo.rol = nuevo_rol
    objetivo.is_superuser = nuevo_rol == Usuario.Rol.SUPERADMIN
    objetivo.is_staff = nuevo_rol in (Usuario.Rol.ADMIN, Usuario.Rol.SUPERADMIN)
    objetivo.save(update_fields=["rol", "is_superuser", "is_staff"])

    cerrar_sesiones_usuario(objetivo)
    registrar_auditoria(
        usuario=actor,
        accion=RegistroAuditoria.Accion.MODIFICAR,
        modelo="Usuario",
        objeto_id=str(objetivo.pk),
        valores_anteriores={"rol": rol_anterior},
        valores_nuevos={"rol": nuevo_rol},
        motivo=motivo or "Cambio de rol",
        request=request,
    )
    return objetivo
