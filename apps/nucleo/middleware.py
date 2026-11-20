"""
Middlewares de seguridad y control de sesión para Luca.

# SEGURIDAD / II.7 / ADR-003 / REQ-16:
- Expiración diferenciada por rol (15 min staff; 30 min vecinos/comerciantes).
- Validación de latido (`ultimo_latido`) para cerrar sesión si el navegador restauró cookies.
- Cabecera `Cache-Control: no-store` en páginas autenticadas (evita botón Atrás con datos).
- Limitación simple de tasa (rate limiting) por IP en rutas sensibles.
"""
import time
from collections import defaultdict

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import logout
from django.http import HttpResponse, JsonResponse
from django.shortcuts import redirect
from django.urls import reverse

# Memoria en proceso para rate limit ligero por IP (complementa a django-axes)
_HISTORIAL_IP: dict[tuple[str, str], list[float]] = defaultdict(list)


def obtener_ip_cliente(request) -> str:
    """Obtiene la IP del cliente considerando el proxy inverso de Vercel."""
    x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if x_forwarded_for:
        return x_forwarded_for.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "127.0.0.1")


class ControlSesionYLatidoMiddleware:
    """
    Aplica caducidad por inactividad según rol, verifica latido de sesión y agrega
    cabeceras `Cache-Control: no-store` para usuarios autenticados.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        usuario = getattr(request, "user", None)
        es_autenticado = bool(usuario and usuario.is_authenticated)

        if es_autenticado:
            es_staff = getattr(usuario, "rol", "") in ("FISCALIZADOR", "ADMIN") or usuario.is_superuser
            ahora = time.time()

            # 1. Expiración por inactividad diferenciada (# II.7)
            limite_inactividad = 900 if es_staff else 1800  # 15 min staff, 30 min resto
            ultimo_acceso = request.session.get("ultimo_movimiento_ts")
            if ultimo_acceso is not None and (ahora - float(ultimo_acceso)) > limite_inactividad:
                return self._cerrar_por_seguridad(
                    request, "Tu sesión se cerró por inactividad para proteger tu cuenta."
                )

            # 2. Verificación de latido (heartbeat) contra restauración de cookies (# ADR-003)
            tolerancia_latido = (
                getattr(settings, "LATIDO_TOLERANCIA_STAFF", 300)
                if es_staff
                else getattr(settings, "LATIDO_TOLERANCIA_PUBLICO", 900)
            )
            ultimo_latido = request.session.get("ultimo_latido_ts")
            if ultimo_latido is not None and (ahora - float(ultimo_latido)) > tolerancia_latido:
                return self._cerrar_por_seguridad(
                    request, "Por su seguridad cerramos su sesión."
                )

            # Actualizar marcas de actividad y expiración en servidor
            request.session["ultimo_movimiento_ts"] = ahora
            if ultimo_latido is None:
                request.session["ultimo_latido_ts"] = ahora
            request.session.set_expiry(0)  # Expira al cerrar navegador (# II.7)

        response = self.get_response(request)

        # SEGURIDAD: Evitar que el botón "Atrás" muestre datos de una sesión cerrada
        if getattr(request, "user", None) and request.user.is_authenticated:
            response["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
            response["Pragma"] = "no-cache"

        return response

    def _cerrar_por_seguridad(self, request, mensaje: str):
        logout(request)
        if request.headers.get("X-Requested-With") == "XMLHttpRequest" or request.path.startswith("/api/"):
            return JsonResponse({"error": mensaje, "sesion_expirada": True}, status=401)
        messages.warning(request, mensaje, fail_silently=True)
        try:
            url_login = reverse("cuentas:ingresar")
        except Exception:
            url_login = "/cuenta/ingresar/"
        return redirect(url_login)


class LimitePeticionesIPMiddleware:
    """
    Protección simple de tasa por IP en rutas sensibles (registro, recuperar clave y búsqueda).
    # SEGURIDAD / REQ-16: Desactivable en pruebas con `RATELIMIT_ACTIVO = False`.
    """

    REGLAS = {
        "/cuenta/registro/": (25, 60),
        "/cuenta/recuperar/": (15, 60),
        "/buscar/": (120, 60),
    }

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if not getattr(settings, "RATELIMIT_ACTIVO", True):
            return self.get_response(request)

        for prefijo, (max_req, ventana) in self.REGLAS.items():
            if request.path.startswith(prefijo):
                ip = obtener_ip_cliente(request)
                clave = (ip, prefijo)
                ahora = time.time()
                marcas = [t for t in _HISTORIAL_IP[clave] if ahora - t < ventana]
                if len(marcas) >= max_req:
                    return HttpResponse(
                        "Has realizado demasiadas solicitudes seguidas. Espera un minuto e inténtalo nuevamente.",
                        status=429,
                        content_type="text/plain; charset=utf-8",
                    )
                marcas.append(ahora)
                _HISTORIAL_IP[clave] = marcas
                break

        return self.get_response(request)
