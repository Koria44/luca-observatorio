"""Rutas de la aplicación `cuentas`."""
from django.contrib.auth import views as auth_views
from django.urls import path

from . import views

app_name = "cuentas"

urlpatterns = [
    path("ingresar/", views.vista_ingresar, name="ingresar"),
    path("salir/", views.vista_salir, name="salir"),
    path("latido/", views.vista_latido, name="latido"),
    path("registro/vecino/", views.vista_registro_vecino, name="registro_vecino"),
    path("registro/comerciante/", views.vista_registro_comerciante, name="registro_comerciante"),
    path("en-revision/", views.vista_en_revision, name="en_revision"),
    path("perfil/", views.vista_perfil, name="perfil"),
    path("zona-comerciante/", views.vista_zona_comerciante_base, name="zona_comerciante"),
    path("api/estado-comerciante/", views.api_estado_comerciante, name="api_estado_comerciante"),
    path("revision/", views.vista_cola_revision_cuentas, name="cola_revision"),
    path("revision/<uuid:usuario_id>/verificar/", views.vista_verificar_cuenta, name="verificar_cuenta"),
    path("revision/<uuid:usuario_id>/aprobar/", views.vista_aprobar_cuenta_final, name="aprobar_cuenta"),
    path(
        "recuperar/",
        auth_views.PasswordResetView.as_view(
            template_name="cuentas/recuperar.html",
            email_template_name="cuentas/recuperar_email.txt",
            success_url="/cuenta/recuperar/enviado/",
        ),
        name="recuperar",
    ),
    path(
        "recuperar/enviado/",
        auth_views.PasswordResetDoneView.as_view(template_name="cuentas/recuperar_enviado.html"),
        name="recuperar_enviado",
    ),
]
