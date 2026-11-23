"""
Módulo centralizado de políticas de autorización — DENEGAR POR DEFECTO (# Prompt 7 / Prompt 8).

Consume `apps.nucleo.permisos_catalogo.CATALOGO_PERMISOS` como fuente única de verdad para los
5 roles definitivos: VECINO, COMERCIANTE, FISCALIZADOR, ADMIN (Admin DIDESE) y SUPERADMIN.

# SEGURIDAD:
- Denegar por defecto: todo permiso no declarado en el catálogo devuelve False.
- Auditoría exclusiva de SUPERADMIN (ningún otro rol tiene `auditoria.*`).
- Elevación temporal obligatoria (30 min) para que SUPERADMIN ejecute acciones operativas de negocio.
- Separación de funciones ("cuatro ojos") incluso para SUPERADMIN elevado.
- Jerarquía estricta: nadie modifica su propio rol ni gestiona un rol igual o superior al suyo,
  ni elimina/degrada al último SUPERADMIN o último ADMIN activo.
"""
from django.conf import settings
from django.db.models import Q
from django.utils import timezone

from apps.nucleo.permisos_catalogo import (
    CATALOGO_PERMISOS,
    JERARQUIA_ROL,
    PERMISOS_OPERATIVOS_CON_ELEVACION,
)

# Roles que componen el personal municipal de supervisión
ROLES_STAFF = ("ADMIN", "FISCALIZADOR", "SUPERADMIN")
ROLES_DECISION_SUPERIOR = ("ADMIN", "SUPERADMIN")

# Alias retrocompatibles -> código canónico del catálogo único (`modulo.accion`)
ALIASES_PERMISOS = {
    "gestionar_roles": "usuario.gestionar_fiscalizadores",
    "otorgar_habilitacion": "habilitacion.otorgar",
    "revocar_habilitacion": "habilitacion.revocar",
    "suspender_habilitacion": "habilitacion.suspender",
    "aplicar_sancion": "sancion.aplicar",
    "gestionar_kill_switch": "publicaciones.pausar",
    "configurar_umbrales": "umbrales.configurar",
    "gestionar_genericos": "generico.proponer_mapeo",
    "revisar_habilitacion": "habilitacion.recomendar",
    "revisar_precio": "precio.revisar",
    "revisar_imagen": "imagen.revisar",
    "revisar_solicitud_producto": "solicitud_producto.revisar",
    "levantar_precio_terreno": "precio.registrar_terreno",
    "ver_documento_privado": "documento.ver_privado",
    "resolver_apelacion": "apelacion.resolver",
    "editar_comercio": "comercio.editar_propio",
    "presentar_apelacion": "descargos.presentar",
    "publicar_precio": "precio.crear_propio",
    "usar_mi_canasta": "lista_compras.gestionar_propia",
    "gestionar_alertas": "alertas.gestionar_propias",
    "reportar_precio": "reporte_ciudadano.crear",
    "ver_auditoria": "auditoria.ver",
    "exportar_auditoria": "auditoria.exportar",
}


def es_superadmin(usuario) -> bool:
    """True solo para usuarios activos con rol SUPERADMIN o flag is_superuser."""
    return bool(
        usuario
        and getattr(usuario, "is_authenticated", False)
        and getattr(usuario, "is_active", False)
        and getattr(usuario, "estado_cuenta", "") == "ACTIVA"
        and (getattr(usuario, "rol", "") == "SUPERADMIN" or getattr(usuario, "is_superuser", False))
    )


def es_administrador(usuario) -> bool:
    """True para ADMIN (Admin DIDESE) o SUPERADMIN activos."""
    return bool(
        usuario
        and getattr(usuario, "is_authenticated", False)
        and getattr(usuario, "is_active", False)
        and getattr(usuario, "estado_cuenta", "") == "ACTIVA"
        and (getattr(usuario, "rol", "") in ("ADMIN", "SUPERADMIN") or getattr(usuario, "is_superuser", False))
    )


def es_staff_activo(usuario) -> bool:
    """True para FISCALIZADOR, ADMIN o SUPERADMIN con cuenta ACTIVA."""
    return bool(
        usuario
        and getattr(usuario, "is_authenticated", False)
        and getattr(usuario, "is_active", False)
        and getattr(usuario, "estado_cuenta", "") == "ACTIVA"
        and (getattr(usuario, "rol", "") in ROLES_STAFF or getattr(usuario, "is_superuser", False))
    )


def tiene_elevacion_activa(usuario) -> bool:
    """True si el SUPERADMIN posee una ElevacionSuperadmin vigente (<= 30 min)."""
    if not es_superadmin(usuario):
        return False
    from apps.gobernanza.models import ElevacionSuperadmin

    return ElevacionSuperadmin.activa_para(usuario) is not None


def es_propietario_comercio(usuario, comercio) -> bool:
    """Un comercio tiene un único propietario titular (`Comercio.propietario`) (# Prompt 8)."""
    if not usuario or not getattr(usuario, "is_authenticated", False) or comercio is None:
        return False
    return comercio.propietario_id == usuario.id


def pertenece_a_sucursal(usuario, sucursal) -> bool:
    """True si el usuario es propietario del comercio dueño de `sucursal`."""
    if not usuario or not getattr(usuario, "is_authenticated", False) or sucursal is None:
        return False
    return es_propietario_comercio(usuario, sucursal.comercio)


def obtener_habilitacion_vigente(comercio):
    """Devuelve la Habilitacion OTORGADA y vigente de `comercio`, o None (# Prompt 7 Sección 2)."""
    if comercio is None or not comercio.activo or comercio.estado != "ACTIVO":
        return None
    from apps.gobernanza.models import Habilitacion

    hoy = timezone.localdate()
    return (
        Habilitacion.objects.filter(
            comercio=comercio,
            estado=Habilitacion.Estado.OTORGADA,
            nivel__gte=Habilitacion.Nivel.SUPERVISADO,
        )
        .filter(Q(vigente_hasta__isnull=True) | Q(vigente_hasta__gte=hoy))
        .order_by("-nivel", "-fecha_otorgamiento")
        .first()
    )


def comercios_visibles_para(usuario):
    """Queryset acotado para evitar IDOR (# Prompt 7 Sección 1.5)."""
    from apps.comercios.models import Comercio

    if not usuario or not usuario.is_authenticated or usuario.estado_cuenta != "ACTIVA":
        return Comercio.objects.none()
    if es_staff_activo(usuario):
        return Comercio.objects.all()
    return Comercio.objects.filter(propietario=usuario)


def sucursales_visibles_para(usuario):
    from apps.comercios.models import Sucursal

    if not usuario or not usuario.is_authenticated or usuario.estado_cuenta != "ACTIVA":
        return Sucursal.objects.none()
    if es_staff_activo(usuario):
        return Sucursal.objects.all()
    return Sucursal.objects.filter(comercio__propietario=usuario)


def precios_visibles_para(usuario):
    from apps.precios.models import Precio

    if not usuario or not usuario.is_authenticated or usuario.estado_cuenta != "ACTIVA":
        return Precio.objects.none()
    if es_staff_activo(usuario):
        return Precio.objects.all()
    return Precio.objects.filter(sucursal__comercio__propietario=usuario)


def puede_gestionar_usuario(actor, objetivo, nuevo_rol: str | None = None) -> bool:
    """
    Reglas estrictas de jerarquía (# Prompt 8 Sección 1.4 y 4.2):
    - Nadie modifica su propio rol ni se auto-suspende.
    - FISCALIZADOR nunca gestiona cuentas de usuario.
    - ADMIN (DIDESE) solo gestiona COMERCIANTE y FISCALIZADOR (nunca ADMIN ni SUPERADMIN).
    - SUPERADMIN puede gestionar todos los roles, pero jamás puede degradar/eliminar al último SUPERADMIN activo.
    """
    if not actor or not getattr(actor, "is_authenticated", False) or objetivo is None:
        return False
    if getattr(actor, "estado_cuenta", "") != "ACTIVA":
        return False
    if actor.id == objetivo.id:
        return False

    rol_actor = "SUPERADMIN" if es_superadmin(actor) else getattr(actor, "rol", "")
    rol_obj = "SUPERADMIN" if (objetivo.rol == "SUPERADMIN" or objetivo.is_superuser) else objetivo.rol

    if rol_actor not in ("ADMIN", "SUPERADMIN"):
        return False

    if rol_actor == "ADMIN":
        # Admin DIDESE no puede tocar otros ADMIN ni SUPERADMIN ni asignar esos roles
        if rol_obj in ("ADMIN", "SUPERADMIN"):
            return False
        if nuevo_rol and nuevo_rol in ("ADMIN", "SUPERADMIN"):
            return False
        return True

    # SUPERADMIN: proteger siempre al último SUPERADMIN activo
    if rol_obj == "SUPERADMIN" and objetivo.is_active and objetivo.estado_cuenta == "ACTIVA":
        from apps.cuentas.models import Usuario

        total_sa = Usuario.objects.filter(
            Q(rol="SUPERADMIN") | Q(is_superuser=True),
            estado_cuenta="ACTIVA",
            is_active=True,
        ).count()
        if total_sa <= 1 and (nuevo_rol is None or nuevo_rol != "SUPERADMIN"):
            return False
    return True


def puede_degradar_o_eliminar_admin(actor, objetivo) -> bool:
    """# SEGURIDAD: Impide degradar/eliminar al último ADMIN o SUPERADMIN activo o cambiar el propio rol."""
    if not puede_gestionar_usuario(actor, objetivo, nuevo_rol="FISCALIZADOR"):
        return False
    if objetivo.rol == "ADMIN" and objetivo.estado_cuenta == "ACTIVA" and objetivo.is_active:
        from apps.cuentas.models import Usuario

        total_admins = Usuario.objects.filter(rol="ADMIN", estado_cuenta="ACTIVA", is_active=True).count()
        if total_admins <= 1:
            return False
    return True


def _rol_efectivo(usuario) -> str:
    if getattr(usuario, "is_superuser", False):
        return "SUPERADMIN"
    return getattr(usuario, "rol", "")


def puede(usuario, accion: str, objeto=None) -> bool:
    """
    Política declarativa DENEGAR POR DEFECTO (# Prompt 8 Sección 2).
    Acepta tanto códigos canónicos (`modulo.accion`) como alias retrocompatibles.
    """
    if not usuario or not getattr(usuario, "is_authenticated", False):
        return False
    if not getattr(usuario, "is_active", False):
        return False
    if getattr(usuario, "estado_cuenta", "") != "ACTIVA":
        return False

    permiso = ALIASES_PERMISOS.get(accion, accion)
    rol = _rol_efectivo(usuario)
    permisos_rol = CATALOGO_PERMISOS.get(rol, frozenset())

    # 1. Caso especial: propietario puede ver sus propios documentos privados
    if permiso == "documento.ver_privado" and rol == "COMERCIANTE" and objeto is not None:
        comercio = getattr(getattr(objeto, "habilitacion", None), "comercio", None)
        return es_propietario_comercio(usuario, comercio)

    # 2. Denegar por defecto si el rol no tiene el permiso en el catálogo único
    if permiso not in permisos_rol:
        return False

    # 3. Auditoría: estrictamente exclusiva de SUPERADMIN
    if permiso.startswith("auditoria."):
        return es_superadmin(usuario)

    # 4. Elevación temporal obligatoria para acciones operativas ejecutadas por SUPERADMIN (# Sección 1.3)
    if (
        rol == "SUPERADMIN"
        and permiso in PERMISOS_OPERATIVOS_CON_ELEVACION
        and getattr(settings, "SUPERADMIN_REQUIERE_ELEVACION", True)
    ):
        if not tiene_elevacion_activa(usuario):
            return False

    # 5. Regla de CUATRO OJOS: nadie aprueba/revisa lo que registró o propuso (# Sección 1.6)
    if permiso in (
        "habilitacion.otorgar",
        "habilitacion.recomendar",
        "precio.revisar",
        "imagen.revisar",
        "solicitud_producto.revisar",
    ) and objeto is not None:
        autor_id = (
            getattr(objeto, "registrado_por_id", None)
            or getattr(objeto, "solicitada_por_id", None)
            or getattr(objeto, "solicitado_por_id", None)
            or getattr(objeto, "subida_por_id", None)
        )
        if autor_id and autor_id == usuario.id:
            return False

    # 6. Apelación: debe resolver un ADMIN o SUPERADMIN (elevado) distinto del sancionador
    if permiso == "apelacion.resolver" and objeto is not None:
        if getattr(getattr(objeto, "sancion", None), "aplicada_por_id", None) == usuario.id:
            return False

    # 7. Acciones sobre comercio propio
    if permiso in ("comercio.editar_propio", "descargos.presentar", "sucursal.editar_propia"):
        if objeto is None:
            return False
        comercio = getattr(objeto, "comercio", objeto)
        return es_propietario_comercio(usuario, comercio)

    # 8. Publicar precio como comerciante: propiedad + sin kill switch + habilitación vigente + alcance
    if permiso == "precio.crear_propio":
        if rol in ("FISCALIZADOR", "ADMIN", "SUPERADMIN"):
            return True
        if objeto is None:
            return False
        sucursal, producto = objeto if isinstance(objeto, tuple) else (objeto, None)
        if not pertenece_a_sucursal(usuario, sucursal):
            return False
        from apps.gobernanza.models import ConfiguracionObservatorio

        cfg = ConfiguracionObservatorio.obtener()
        if cfg.kill_switch_global or sucursal.comercio_id in (cfg.comercios_pausados or []):
            return False
        hab = obtener_habilitacion_vigente(sucursal.comercio)
        if not hab:
            return False
        if producto is not None and not hab.cubre_categoria_y_sucursal(producto.categoria_id, sucursal.id):
            return False
        return True

    return True
