"""
Decoradores y mixins de autorización por rol y estado de cuenta.

# SEGURIDAD / REQ-08: Toda verificación de permisos se aplica en el servidor.
# Un comerciante en estado PENDIENTE, RECHAZADA o SUSPENDIDA jamás puede acceder
# a vistas de gestión ni APIs internas.
"""
from functools import wraps

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import JsonResponse
from django.shortcuts import redirect


def _es_peticion_api(request) -> bool:
    return (
        request.headers.get("X-Requested-With") == "XMLHttpRequest"
        or request.path.startswith("/api/")
        or "application/json" in request.headers.get("Accept", "")
    )


def rol_requerido(*roles_permitidos):
    """Restringe una vista a usuarios autenticados con cuenta ACTIVA y uno de los roles dados."""

    def decorador(vista):
        @login_required
        @wraps(vista)
        def envuelta(request, *args, **kwargs):
            usuario = request.user
            # Un comerciante aún no activo siempre va a su pantalla de estado o recibe 403 en API
            if usuario.rol == "COMERCIANTE" and usuario.estado_cuenta != "ACTIVA":
                if _es_peticion_api(request):
                    return JsonResponse(
                        {"error": "Tu cuenta de comerciante aún no está activa."},
                        status=403,
                    )
                return redirect("cuentas:en_revision")

            if usuario.estado_cuenta != "ACTIVA" and not usuario.is_superuser:
                if _es_peticion_api(request):
                    return JsonResponse({"error": "Cuenta inactiva o suspendida."}, status=403)
                raise PermissionDenied("Tu cuenta no está activa para realizar esta acción.")

            if usuario.rol not in roles_permitidos and not usuario.is_superuser:
                if _es_peticion_api(request):
                    return JsonResponse({"error": "No tienes permisos para esta acción."}, status=403)
                raise PermissionDenied("No tienes permisos para acceder a esta sección.")

            return vista(request, *args, **kwargs)

        return envuelta

    return decorador


def comerciante_activo_requerido(vista):
    """
    Exige usuario autenticado con rol COMERCIANTE (o ADMIN) y `estado_cuenta == ACTIVA`.
    # SEGURIDAD / II.5: Un comerciante PENDIENTE recibe 403 en API/AJAX o redirección
    a `/cuenta/en-revision/` en vistas HTML.
    """

    @login_required
    @wraps(vista)
    def envuelta(request, *args, **kwargs):
        usuario = request.user
        if usuario.rol == "COMERCIANTE" and usuario.estado_cuenta != "ACTIVA":
            if _es_peticion_api(request):
                return JsonResponse(
                    {"error": "Tu cuenta de comerciante está en revisión y no puede operar aún."},
                    status=403,
                )
            messages.info(request, "Tu cuenta de comerciante todavía está en revisión.")
            return redirect("cuentas:en_revision")

        if usuario.rol not in ("COMERCIANTE", "ADMIN") and not usuario.is_superuser:
            if _es_peticion_api(request):
                return JsonResponse({"error": "Acceso restringido a comerciantes activos."}, status=403)
            raise PermissionDenied("Esta sección es exclusiva para comerciantes registrados y activos.")

        return vista(request, *args, **kwargs)

    return envuelta


def solo_fiscalizador_o_admin(vista):
    """Restringe la vista a fiscalizadores municipales y administradores DIDESE."""
    return rol_requerido("FISCALIZADOR", "ADMIN")(vista)


def solo_admin(vista):
    """Restringe la vista exclusivamente a administradores DIDESE."""
    return rol_requerido("ADMIN")(vista)
