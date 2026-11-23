"""
Catálogo declarativo único de permisos por rol — Fuente única de verdad (# Prompt 8 Sección 2).

Define exactamente 5 roles: VECINO, COMERCIANTE, FISCALIZADOR, ADMIN (Admin DIDESE) y SUPERADMIN.
Todo permiso que no figure explícitamente en el catálogo está DENEGADO por defecto.
"""

ROLES_ORDENADOS = ("VECINO", "COMERCIANTE", "FISCALIZADOR", "ADMIN", "SUPERADMIN")

JERARQUIA_ROL = {
    "VECINO": 1,
    "COMERCIANTE": 2,
    "FISCALIZADOR": 3,
    "ADMIN": 4,
    "SUPERADMIN": 5,
}

# Acciones operativas de negocio que el SUPERADMIN solo puede ejecutar con elevación temporal (30 min)
PERMISOS_OPERATIVOS_CON_ELEVACION = frozenset({
    "precio.revisar",
    "precio.registrar_terreno",
    "habilitacion.otorgar",
    "habilitacion.rechazar",
    "habilitacion.suspender",
    "habilitacion.revocar",
    "nivel_confianza.cambiar",
    "sancion.aplicar",
    "apelacion.resolver",
    "catalogo.gestionar",
    "publicaciones.pausar",
    "umbrales.configurar",
    "carga_masiva.crear_propia",
})

PERMISOS_VECINO = frozenset({
    "portal.consultar",
    "lista_compras.gestionar_propia",
    "alertas.gestionar_propias",
    "reporte_ciudadano.crear",
    "cuenta.editar_propia",
    "cuenta.solicitar_baja",
})

PERMISOS_COMERCIANTE = frozenset({
    "portal.consultar",
    "reporte_ciudadano.crear",
    "habilitacion.solicitar",
    "habilitacion.ver_propia",
    "documento.subir_propio",
    "convenio.aceptar",
    "comercio.editar_propio",
    "sucursal.proponer",
    "sucursal.editar_propia",
    "logo.proponer",
    "precio.crear_propio",
    "precio.retirar_propio",
    "carga_masiva.crear_propia",
    "imagen_producto.proponer",
    "solicitud_producto.crear",
    "descargos.presentar",
    "historial_funcional.ver_propio",
    "reporte.exportar_propio",
    "cuenta.editar_propia",
})

PERMISOS_FISCALIZADOR = frozenset({
    "portal.consultar",
    "reporte_ciudadano.crear",
    "caso.tomar",
    "comercio.revisar",
    "documento.ver_privado",
    "habilitacion.recomendar",
    "precio.revisar",
    "precio.registrar_terreno",
    "verificacion_terreno.registrar",
    "imagen.revisar",
    "imagen.subir_oficial",
    "imagen.fijar_principal",
    "reporte_ciudadano.moderar",
    "solicitud_producto.revisar",
    "generico.proponer_mapeo",
    "sancion.proponer",
    "reporte_operativo.ver",
    "historial_funcional.ver",
})

PERMISOS_ADMIN = PERMISOS_FISCALIZADOR | frozenset({
    "habilitacion.otorgar",
    "habilitacion.rechazar",
    "habilitacion.suspender",
    "habilitacion.revocar",
    "nivel_confianza.cambiar",
    "comercio.aprobar_final",
    "usuario.gestionar_fiscalizadores",
    "usuario.gestionar_comerciantes",
    "sancion.aplicar",
    "apelacion.resolver",
    "catalogo.gestionar",
    "banner.gestionar",
    "umbrales.configurar",
    "publicaciones.pausar",
    "dashboard.ver_global",
    "reporte.generar",
    "datos_abiertos.publicar",
    "verificacion_requisitos.gestionar",
    "carga_masiva.crear_propia",
})

PERMISOS_SUPERADMIN_GOBIERNO = frozenset({
    "portal.consultar",
    "reporte_ciudadano.crear",
    "usuario.gestionar_todos",
    "auditoria.ver",
    "auditoria.exportar",
    "auditoria.verificar_integridad",
    "sistema.configurar",
    "feature_flags.gestionar",
    "mantenimiento.activar",
    "respaldo.ver_estado",
    "respaldo.disparar",
    "salud.ver",
    "seguridad.ver_sesiones",
    "seguridad.cerrar_sesiones",
    "seguridad.desbloquear_cuentas",
    "datos_personales.exportar",
    "datos_personales.anonimizar",
    "django_admin.acceder",
    "elevacion.solicitar",
    "dashboard.ver_global",
    "reporte.generar",
    "historial_funcional.ver",
})

CATALOGO_PERMISOS = {
    "VECINO": PERMISOS_VECINO,
    "COMERCIANTE": PERMISOS_COMERCIANTE,
    "FISCALIZADOR": PERMISOS_FISCALIZADOR,
    "ADMIN": PERMISOS_ADMIN,
    "SUPERADMIN": PERMISOS_SUPERADMIN_GOBIERNO | PERMISOS_ADMIN,
}


def sincronizar_grupos_django() -> None:
    """Crea o sincroniza los 5 grupos de Django correspondientes a cada rol (# Sección 1.2)."""
    from django.contrib.auth.models import Group

    for rol in ROLES_ORDENADOS:
        Group.objects.get_or_create(name=f"ROL_{rol}")


def generar_tabla_markdown_permisos() -> str:
    """Genera la tabla Markdown oficial `docs/gobernanza/matriz_permisos.md` desde el catálogo."""
    todos = sorted(set().union(*CATALOGO_PERMISOS.values()))
    lineas = [
        "# Matriz Oficial de Permisos por Rol (Generada desde `permisos_catalogo.py`)",
        "",
        "> **Nota:** Auditoría (`auditoria.*`) es exclusiva de **SUPERADMIN**. `†` indica acción operativa de SUPERADMIN sujeta a elevación temporal de 30 min.",
        "",
        "| Permiso | VECINO | COMERCIANTE | FISCALIZADOR | ADMIN_DIDESE | SUPERADMIN |",
        "|---|---|---|---|---|---|",
    ]
    for perm in todos:
        fila = [f"`{perm}`"]
        for rol in ROLES_ORDENADOS:
            tiene = perm in CATALOGO_PERMISOS[rol]
            if tiene and rol == "SUPERADMIN" and perm in PERMISOS_OPERATIVOS_CON_ELEVACION:
                fila.append("✔†")
            else:
                fila.append("✔" if tiene else "—")
        lineas.append("| " + " | ".join(fila) + " |")
    return "\n".join(lineas) + "\n"
