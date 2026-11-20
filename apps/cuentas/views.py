"""
Vistas de autenticación, latido de sesión, registro y flujo de aprobación de comerciantes.

# REQ-08: Roles, permisos y flujo PENDIENTE -> VERIFICADA -> ACTIVA.
# SEGURIDAD / II.7: Cierre de sesión real, latido y bloqueo de comerciantes no activos.
"""
import time

from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.nucleo.permisos import (
    comerciante_activo_requerido,
    solo_admin,
    solo_fiscalizador_o_admin,
)

from .forms import (
    FormularioLogin,
    FormularioPerfil,
    FormularioRegistroComerciante,
    FormularioRegistroVecino,
)
from .models import Usuario


def _registrar_evento_auditoria(usuario, accion: str, modelo: str, objeto_id: str, request, nuevos=None, anteriores=None):
    """Enlace desacoplado con `apps.auditoria` (se activa automáticamente desde Fase 3)."""
    try:
        from apps.auditoria.servicios import registrar_auditoria

        registrar_auditoria(
            usuario=usuario,
            accion=accion,
            modelo=modelo,
            objeto_id=str(objeto_id),
            valores_anteriores=anteriores or {},
            valores_nuevos=nuevos or {},
            request=request,
        )
    except Exception:
        pass


def vista_ingresar(request):
    """Inicio de sesión con redirección según rol y estado de cuenta."""
    if request.user.is_authenticated:
        if request.user.rol == Usuario.Rol.COMERCIANTE and request.user.estado_cuenta != Usuario.EstadoCuenta.ACTIVA:
            return redirect("cuentas:en_revision")
        return redirect("portal:inicio")

    form = FormularioLogin(request=request, data=request.POST or None)
    if request.method == "POST" and form.is_valid():
        usuario = form.usuario_autenticado
        login(request, usuario)
        ahora = time.time()
        request.session["ultimo_movimiento_ts"] = ahora
        request.session["ultimo_latido_ts"] = ahora
        request.session.set_expiry(0)

        usuario.ultimo_acceso = timezone.now()
        usuario.save(update_fields=["ultimo_acceso"])
        _registrar_evento_auditoria(usuario, "LOGIN", "Usuario", usuario.id, request)

        if usuario.rol == Usuario.Rol.COMERCIANTE and usuario.estado_cuenta != Usuario.EstadoCuenta.ACTIVA:
            return redirect("cuentas:en_revision")

        messages.success(request, f"¡Hola, {usuario.nombres}! Iniciaste sesión correctamente.")
        destino = request.POST.get("next") or request.GET.get("next") or "portal:inicio"
        return redirect(destino)

    return render(request, "cuentas/login.html", {"form": form})


@require_POST
def vista_salir(request):
    """Cierra la sesión en servidor y registra auditoría LOGOUT (# II.7 / REQ-15)."""
    if request.user.is_authenticated:
        _registrar_evento_auditoria(request.user, "LOGOUT", "Usuario", request.user.id, request)
        logout(request)
        messages.info(request, "Cerraste tu sesión de forma segura. ¡Hasta pronto!")
    return redirect("portal:inicio")


@login_required
@require_POST
def vista_latido(request):
    """
    Actualiza el latido de sesión (`ultimo_latido_ts`) mientras la pestaña está abierta.
    # SEGURIDAD / ADR-003: Permite detectar cookies restauradas tras cerrar el navegador.
    """
    ahora = time.time()
    request.session["ultimo_latido_ts"] = ahora
    if request.POST.get("renovar_actividad") == "1":
        request.session["ultimo_movimiento_ts"] = ahora
    es_staff = request.user.es_staff_observatorio
    return JsonResponse(
        {
            "ok": True,
            "limite_inactividad": 900 if es_staff else 1800,
        }
    )


def vista_registro_vecino(request):
    """Registro sencillo para vecinos de Pedro Aguirre Cerda."""
    if request.user.is_authenticated:
        return redirect("portal:inicio")
    form = FormularioRegistroVecino(request.POST or None)
    if request.method == "POST" and form.is_valid():
        usuario = form.guardar()
        _registrar_evento_auditoria(usuario, "CREAR", "Usuario", usuario.id, request, {"rol": "VECINO"})
        messages.success(request, "¡Cuenta creada con éxito! Ya puedes ingresar con tu correo.")
        return redirect("cuentas:ingresar")
    return render(request, "cuentas/registro_vecino.html", {"form": form})


def vista_registro_comerciante(request):
    """
    Registro guiado de comerciantes en pasos.
    # REQ-08 / II.5: Crea cuenta PENDIENTE y redirige a la pantalla "Tu cuenta está en revisión".
    """
    if request.user.is_authenticated:
        return redirect("cuentas:en_revision")
    form = FormularioRegistroComerciante(request.POST or None)
    if request.method == "POST" and form.is_valid():
        usuario = form.guardar()
        _registrar_evento_auditoria(
            usuario,
            "CREAR",
            "Usuario",
            usuario.id,
            request,
            {"rol": "COMERCIANTE", "estado_cuenta": "PENDIENTE"},
        )
        # Inicia sesión para mostrar inmediatamente el estado amable "en revisión"
        login(request, usuario, backend="django.contrib.auth.backends.ModelBackend")
        ahora = time.time()
        request.session["ultimo_movimiento_ts"] = ahora
        request.session["ultimo_latido_ts"] = ahora
        request.session.set_expiry(0)
        messages.success(request, "Recibimos tu solicitud de comercio. Revisa los próximos pasos.")
        return redirect("cuentas:en_revision")
    return render(request, "cuentas/registro_comerciante.html", {"form": form})


@login_required
def vista_en_revision(request):
    """Pantalla amable para comerciantes cuya cuenta aún no está ACTIVA (# II.5)."""
    if request.user.rol != Usuario.Rol.COMERCIANTE or request.user.estado_cuenta == Usuario.EstadoCuenta.ACTIVA:
        return redirect("portal:inicio")
    return render(request, "cuentas/en_revision.html", {"usuario": request.user})


@login_required
def vista_perfil(request):
    """Consulta y actualización básica del perfil propio."""
    if request.user.rol == Usuario.Rol.COMERCIANTE and request.user.estado_cuenta != Usuario.EstadoCuenta.ACTIVA:
        return redirect("cuentas:en_revision")
    form = FormularioPerfil(request.POST or None, instance=request.user)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Tus datos de contacto se actualizaron correctamente.")
        return redirect("cuentas:perfil")
    return render(request, "cuentas/perfil.html", {"form": form})


@comerciante_activo_requerido
def vista_zona_comerciante_base(request):
    """Punto de entrada protegido para comerciantes ACTIVOS (ampliado en Fase 5)."""
    return render(request, "cuentas/zona_comerciante_base.html")


@comerciante_activo_requerido
def api_estado_comerciante(request):
    """Endpoint JSON protegido por `comerciante_activo_requerido` (# SEGURIDAD / II.5)."""
    return JsonResponse({"ok": True, "comerciante": request.user.email, "estado": request.user.estado_cuenta})


@solo_fiscalizador_o_admin
def vista_cola_revision_cuentas(request):
    """Cola de verificación (fiscalizador) y aprobación final (admin) de comerciantes (# REQ-08)."""
    cuentas = Usuario.objects.filter(rol=Usuario.Rol.COMERCIANTE).order_by("-creado_en")
    return render(request, "cuentas/cola_revision.html", {"cuentas": cuentas})


@solo_fiscalizador_o_admin
@require_POST
def vista_verificar_cuenta(request, usuario_id):
    """Un fiscalizador (o admin) marca una cuenta PENDIENTE como VERIFICADA o RECHAZADA."""
    objetivo = get_object_or_404(Usuario, id=usuario_id, rol=Usuario.Rol.COMERCIANTE)
    accion = request.POST.get("accion")
    estado_anterior = objetivo.estado_cuenta

    if accion == "verificar":
        objetivo.marcar_verificada(request.user)
        _registrar_evento_auditoria(
            request.user,
            "MODIFICAR",
            "Usuario",
            objetivo.id,
            request,
            nuevos={"estado_cuenta": objetivo.estado_cuenta},
            anteriores={"estado_cuenta": estado_anterior},
        )
        messages.success(request, f"Cuenta de {objetivo.nombre_completo} marcada como VERIFICADA.")
    elif accion == "rechazar":
        motivo = request.POST.get("motivo", "").strip()
        if not motivo:
            messages.error(request, "Debes escribir el motivo del rechazo.")
        else:
            objetivo.rechazar_cuenta(request.user, motivo)
            _registrar_evento_auditoria(
                request.user,
                "RECHAZAR",
                "Usuario",
                objetivo.id,
                request,
                nuevos={"estado_cuenta": objetivo.estado_cuenta, "motivo": motivo},
                anteriores={"estado_cuenta": estado_anterior},
            )
            messages.warning(request, f"Cuenta de {objetivo.nombre_completo} rechazada.")
    return redirect("cuentas:cola_revision")


@solo_admin
@require_POST
def vista_aprobar_cuenta_final(request, usuario_id):
    """Un administrador DIDESE da la aprobación final (`ACTIVA`) al comerciante."""
    objetivo = get_object_or_404(Usuario, id=usuario_id, rol=Usuario.Rol.COMERCIANTE)
    estado_anterior = objetivo.estado_cuenta
    objetivo.aprobar_cuenta(request.user)
    _registrar_evento_auditoria(
        request.user,
        "APROBAR",
        "Usuario",
        objetivo.id,
        request,
        nuevos={"estado_cuenta": objetivo.estado_cuenta},
        anteriores={"estado_cuenta": estado_anterior},
    )
    messages.success(request, f"¡Cuenta de {objetivo.nombre_completo} aprobada y ACTIVA!")
    return redirect("cuentas:cola_revision")
