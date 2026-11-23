"""
Enrutamiento principal de URLs de Luca — Observatorio de Precios (PAC).
"""
from django.conf import settings
from django.contrib import admin
from django.http import JsonResponse
from django.shortcuts import render
from django.urls import include, path
from django.views.static import serve


from apps.comercios import api_mapa, geo_proxy

def vista_salud(request):
    """Endpoint liviano de verificación de estado del servicio (# REQ-16)."""
    return JsonResponse(
        {
            "estado": "ok",
            "servicio": "Luca — Observatorio de Precios PAC",
        }
    )


def vista_inicio_base(request):
    """Vista inicial temporal de Fase 0/1 (se reemplazará por apps.portal en Fase 4)."""
    return render(request, "portal/inicio_base.html")


urlpatterns = [
    path("", include("apps.portal.urls")),
    path("salud/", vista_salud, name="salud"),
    path("api/mapa/config/", api_mapa.api_mapa_config, name="api_mapa_config"),
    path("api/mapa/sucursales/", api_mapa.api_mapa_sucursales, name="api_mapa_sucursales"),
    path("api/geo/autocompletar/", geo_proxy.api_geo_autocompletar, name="api_geo_autocompletar"),
    path("api/geo/buscar/", geo_proxy.api_geo_buscar, name="api_geo_buscar"),
    path("api/geo/inversa/", geo_proxy.api_geo_inversa, name="api_geo_inversa"),
    path("cuenta/", include("apps.cuentas.urls")),
    path("catalogo/", include("apps.catalogo.urls")),
    path("comercios/", include("apps.comercios.urls")),
    path("precios/", include("apps.precios.urls")),
    path("panel/", include("apps.panel.urls")),
    path("reportes/", include("apps.reportes.urls")),
    path("auditoria/", include("apps.auditoria.urls")),
    path("superadmin/", include("apps.gobernanza.urls")),
    path("verificacion/", include("apps.verificacion.urls")),
    path(settings.DJANGO_ADMIN_URL, admin.site.urls),
]

# En desarrollo local servimos SOLO `media/publico/`; `media/pendientes/` queda privado (# SEGURIDAD)
if settings.DEBUG:
    urlpatterns += [
        path(
            "media/publico/<path:path>",
            serve,
            {"document_root": settings.MEDIA_ROOT / "publico"},
        ),
    ]
