"""
Vistas de gestión segura de logos de comercios y fotos de productos (# REQ-01, 02, 12, 15, 16).

# SEGURIDAD:
- Verifica rol y propiedad (IDOR -> 403).
- Comerciantes nunca pueden aprobar su propia imagen ni marcarla como principal.
- Las imágenes pendientes se sirven únicamente mediante vista autenticada y autorizada.
- Toda subida, aprobación, rechazo, cambio de principal o retiro queda en `RegistroAuditoria`.
"""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.html import strip_tags
from django.views.decorators.http import require_POST

from apps.auditoria.servicios import registrar_auditoria
from apps.catalogo.models import ImagenProducto, Producto, ReporteImagen
from apps.comercios.models import Comercio
from apps.nucleo.imagenes import (
    eliminar_de_publico,
    leer_bytes_pendiente,
    procesar_imagen_producto,
    procesar_logo_comercio,
    promover_a_publico,
    verificar_limite_subidas,
)
from apps.nucleo.permisos import (
    comerciante_activo_requerido,
    rol_requerido,
    solo_fiscalizador_o_admin,
)

MOTIVOS_RECHAZO_FRECUENTES = [
    "No corresponde al producto",
    "Mala calidad o desenfocada",
    "Tiene texto promocional o publicidad",
    "Contiene personas identificables",
    "Sin derechos de uso acreditados",
]


@comerciante_activo_requerido
def vista_subir_logo_comercio(request, comercio_id):
    """Permite a un comerciante activo subir/reemplazar el logo de SU comercio (queda PENDIENTE)."""
    comercio = get_object_or_404(Comercio, pk=comercio_id)
    es_staff = request.user.es_staff_observatorio
    if not es_staff and comercio.propietario_id != request.user.id:
        registrar_auditoria(
            usuario=request.user,
            accion="RECHAZAR",
            modelo="ComercioLogo",
            objeto_id=str(comercio.pk),
            valores_nuevos={"motivo": "Intento IDOR al subir logo ajeno"},
            request=request,
        )
        raise PermissionDenied("No puedes modificar el logo de otro comercio.")

    if request.method == "POST":
        archivo = request.FILES.get("logo")
        try:
            verificar_limite_subidas(request.user)
            publico_directo = es_staff
            res = procesar_logo_comercio(archivo, publico=publico_directo)
            estado_anterior = comercio.logo_estado
            comercio.logo = res["logo"]
            comercio.logo_miniatura = res["logo_miniatura"]
            comercio.logo_estado = (
                Comercio.EstadoLogo.APROBADO if publico_directo else Comercio.EstadoLogo.PENDIENTE
            )
            comercio.logo_motivo_rechazo = ""
            if publico_directo:
                comercio.logo_revisado_por = request.user
                comercio.logo_fecha_revision = timezone.now()
            comercio.save()
            registrar_auditoria(
                usuario=request.user,
                accion="MODIFICAR",
                modelo="ComercioLogo",
                objeto_id=str(comercio.pk),
                valores_anteriores={"logo_estado": estado_anterior},
                valores_nuevos={"logo_estado": comercio.logo_estado, "logo": comercio.logo},
                request=request,
            )
            messages.success(
                request,
                "Logo publicado correctamente."
                if publico_directo
                else "Logo subido correctamente. Quedó en revisión por un fiscalizador.",
            )
            return redirect("panel:comerciante" if not es_staff else "comercios:mis_sucursales")
        except ValidationError as exc:
            messages.error(request, exc.message)

    return render(request, "comercios/subir_logo.html", {"comercio": comercio})


@rol_requerido("COMERCIANTE", "FISCALIZADOR", "ADMIN")
def vista_subir_foto_producto(request, producto_id):
    """
    Sube una fotografía de producto (# Sección 3.3):
    - Comerciante: exige declaración de derechos, máx. 5 pendientes por producto, queda PENDIENTE,
      y jamás puede marcar `es_principal`.
    - Fiscalizador / Admin: queda APROBADA de inmediato y puede fijarla como imagen principal.
    """
    producto = get_object_or_404(Producto, pk=producto_id, activo=True)
    es_staff = request.user.es_staff_observatorio
    comercio_usuario = None if es_staff else Comercio.objects.filter(propietario=request.user).first()

    if request.method == "POST":
        archivo = request.FILES.get("imagen")
        alt_txt = strip_tags(request.POST.get("texto_alternativo", "")).strip()[:200]
        if not alt_txt:
            alt_txt = f"Foto de {producto.nombre_completo}"

        if not es_staff:
            if request.POST.get("es_principal") in ("1", "on", "true"):
                raise PermissionDenied("Solo un fiscalizador o administrador puede definir la imagen principal.")
            if request.POST.get("declaracion_derechos") not in ("1", "on", "true"):
                messages.error(request, "Debes marcar la declaración de derechos de uso para subir una foto.")
                return render(request, "catalogo/subir_foto.html", {"producto": producto, "es_staff": es_staff})
            pendientes_count = ImagenProducto.objects.filter(
                producto=producto, comercio=comercio_usuario, estado=ImagenProducto.Estado.PENDIENTE
            ).count()
            if pendientes_count >= 5:
                messages.error(request, "Ya tienes 5 fotos en revisión para este producto.")
                return render(request, "catalogo/subir_foto.html", {"producto": producto, "es_staff": es_staff})

        try:
            verificar_limite_subidas(request.user)
            datos_img = procesar_imagen_producto(archivo, publico=es_staff)
            quiere_principal = es_staff and request.POST.get("es_principal") in ("1", "on", "true")

            with transaction.atomic():
                if quiere_principal:
                    ImagenProducto.objects.filter(producto=producto, es_principal=True).update(es_principal=False)
                rol_orig = (
                    ImagenProducto.RolOrigen.ADMIN
                    if request.user.rol == "ADMIN"
                    else ImagenProducto.RolOrigen.FISCALIZADOR
                    if request.user.rol == "FISCALIZADOR"
                    else ImagenProducto.RolOrigen.COMERCIANTE
                )
                img_obj = ImagenProducto.objects.create(
                    producto=producto,
                    comercio=comercio_usuario,
                    subida_por=request.user,
                    rol_origen=rol_orig,
                    archivo_miniatura=datos_img["archivo_miniatura"],
                    archivo_media=datos_img["archivo_media"],
                    archivo_grande=datos_img["archivo_grande"],
                    ancho=datos_img["ancho"],
                    alto=datos_img["alto"],
                    tamano_bytes=datos_img["tamano_bytes"],
                    texto_alternativo=alt_txt,
                    estado=ImagenProducto.Estado.APROBADA if es_staff else ImagenProducto.Estado.PENDIENTE,
                    revisada_por=request.user if es_staff else None,
                    fecha_revision=timezone.now() if es_staff else None,
                    es_principal=quiere_principal,
                    declaracion_derechos=True,
                )

            registrar_auditoria(
                usuario=request.user,
                accion="CREAR",
                modelo="ImagenProducto",
                objeto_id=str(img_obj.pk),
                valores_nuevos={"producto_id": producto.id, "estado": img_obj.estado, "es_principal": img_obj.es_principal},
                request=request,
            )
            messages.success(
                request,
                "Foto publicada correctamente."
                if es_staff
                else "Foto enviada a revisión municipal. Se mostrará cuando sea aprobada.",
            )
            return redirect("portal:comparar", producto_id=producto.id)
        except ValidationError as exc:
            messages.error(request, exc.message)

    return render(request, "catalogo/subir_foto.html", {"producto": producto, "es_staff": es_staff})


@solo_fiscalizador_o_admin
def vista_cola_revision_imagenes(request):
    """Cola unificada de logos y fotos de productos pendientes de revisión (# Sección 3.3)."""
    fotos_pend = (
        ImagenProducto.objects.filter(estado=ImagenProducto.Estado.PENDIENTE)
        .select_related("producto", "producto__marca", "comercio", "subida_por")
        .order_by("creado_en")
    )
    logos_pend = Comercio.objects.filter(logo_estado=Comercio.EstadoLogo.PENDIENTE).select_related("propietario")
    reportes = ReporteImagen.objects.filter(atendido=False).select_related("imagen", "imagen__producto")[:20]
    return render(
        request,
        "catalogo/cola_revision_imagenes.html",
        {
            "fotos_pend": fotos_pend,
            "logos_pend": logos_pend,
            "reportes": reportes,
            "motivos_frecuentes": MOTIVOS_RECHAZO_FRECUENTES,
        },
    )


@solo_fiscalizador_o_admin
@require_POST
def vista_decidir_imagen_producto(request, imagen_id):
    """Aprueba (opcionalmente como principal), rechaza o retira una foto de producto."""
    img = get_object_or_404(ImagenProducto, pk=imagen_id)
    accion = request.POST.get("accion")
    estado_prev = img.estado

    if accion in ("aprobar", "aprobar_principal"):
        with transaction.atomic():
            img.archivo_miniatura = promover_a_publico(img.archivo_miniatura)
            img.archivo_media = promover_a_publico(img.archivo_media)
            img.archivo_grande = promover_a_publico(img.archivo_grande)
            img.estado = ImagenProducto.Estado.APROBADA
            img.revisada_por = request.user
            img.fecha_revision = timezone.now()
            img.motivo_rechazo = ""
            if accion == "aprobar_principal":
                ImagenProducto.objects.filter(producto=img.producto, es_principal=True).exclude(pk=img.pk).update(es_principal=False)
                img.es_principal = True
            img.save()
        registrar_auditoria(
            usuario=request.user,
            accion="APROBAR",
            modelo="ImagenProducto",
            objeto_id=str(img.pk),
            valores_anteriores={"estado": estado_prev},
            valores_nuevos={"estado": img.estado, "es_principal": img.es_principal},
            request=request,
        )
        messages.success(request, f"Foto #{img.pk} aprobada correctamente.")

    elif accion == "rechazar":
        motivo = request.POST.get("motivo", "").strip()
        if not motivo:
            messages.error(request, "Debes indicar un motivo de rechazo.")
            return redirect("catalogo:cola_imagenes")
        eliminar_de_publico(img.archivo_miniatura)
        eliminar_de_publico(img.archivo_media)
        eliminar_de_publico(img.archivo_grande)
        img.estado = ImagenProducto.Estado.RECHAZADA
        img.es_principal = False
        img.motivo_rechazo = motivo
        img.revisada_por = request.user
        img.fecha_revision = timezone.now()
        img.save()
        registrar_auditoria(
            usuario=request.user,
            accion="RECHAZAR",
            modelo="ImagenProducto",
            objeto_id=str(img.pk),
            valores_anteriores={"estado": estado_prev},
            valores_nuevos={"estado": img.estado, "motivo": motivo},
            request=request,
        )
        messages.warning(request, f"Foto #{img.pk} rechazada.")

    elif accion == "principal" and img.estado == ImagenProducto.Estado.APROBADA:
        with transaction.atomic():
            ImagenProducto.objects.filter(producto=img.producto, es_principal=True).exclude(pk=img.pk).update(es_principal=False)
            img.es_principal = True
            img.save(update_fields=["es_principal"])
        registrar_auditoria(
            usuario=request.user,
            accion="MODIFICAR",
            modelo="ImagenProducto",
            objeto_id=str(img.pk),
            valores_nuevos={"es_principal": True},
            request=request,
        )
        messages.success(request, "Imagen principal del producto actualizada.")

    elif accion == "retirar":
        eliminar_de_publico(img.archivo_miniatura)
        eliminar_de_publico(img.archivo_media)
        eliminar_de_publico(img.archivo_grande)
        img.estado = ImagenProducto.Estado.RETIRADA
        img.es_principal = False
        img.save()
        registrar_auditoria(
            usuario=request.user,
            accion="ELIMINAR",
            modelo="ImagenProducto",
            objeto_id=str(img.pk),
            valores_anteriores={"estado": estado_prev},
            valores_nuevos={"estado": img.estado},
            request=request,
        )
        messages.info(request, f"Foto #{img.pk} retirada del portal público.")

    return redirect(request.POST.get("next") or "catalogo:cola_imagenes")


@solo_fiscalizador_o_admin
@require_POST
def vista_decidir_logo_comercio(request, comercio_id):
    """Aprueba o rechaza el logo pendiente de un comercio."""
    com = get_object_or_404(Comercio, pk=comercio_id)
    accion = request.POST.get("accion")
    estado_prev = com.logo_estado

    if accion == "aprobar":
        com.logo = promover_a_publico(com.logo)
        com.logo_miniatura = promover_a_publico(com.logo_miniatura)
        com.logo_estado = Comercio.EstadoLogo.APROBADO
        com.logo_motivo_rechazo = ""
        com.logo_revisado_por = request.user
        com.logo_fecha_revision = timezone.now()
        com.save()
        registrar_auditoria(
            usuario=request.user,
            accion="APROBAR",
            modelo="ComercioLogo",
            objeto_id=str(com.pk),
            valores_anteriores={"logo_estado": estado_prev},
            valores_nuevos={"logo_estado": com.logo_estado},
            request=request,
        )
        messages.success(request, f"Logo de {com.nombre_fantasia} aprobado y visible en el portal.")
    elif accion == "rechazar":
        motivo = request.POST.get("motivo", "").strip()
        if not motivo:
            messages.error(request, "Debes indicar un motivo de rechazo para el logo.")
            return redirect("catalogo:cola_imagenes")
        eliminar_de_publico(com.logo)
        eliminar_de_publico(com.logo_miniatura)
        com.logo_estado = Comercio.EstadoLogo.RECHAZADO
        com.logo_motivo_rechazo = motivo
        com.logo_revisado_por = request.user
        com.logo_fecha_revision = timezone.now()
        com.save()
        registrar_auditoria(
            usuario=request.user,
            accion="RECHAZAR",
            modelo="ComercioLogo",
            objeto_id=str(com.pk),
            valores_anteriores={"logo_estado": estado_prev},
            valores_nuevos={"logo_estado": com.logo_estado, "motivo": motivo},
            request=request,
        )
        messages.warning(request, f"Logo de {com.nombre_fantasia} rechazado.")

    return redirect("catalogo:cola_imagenes")


@require_POST
def vista_reportar_imagen(request, imagen_id):
    """Permite a cualquier visitante o usuario reportar una foto para revisión del fiscalizador."""
    img = get_object_or_404(ImagenProducto, pk=imagen_id, estado=ImagenProducto.Estado.APROBADA)
    motivo = strip_tags(request.POST.get("motivo", "Imagen inapropiada o no corresponde")).strip()[:220]
    ReporteImagen.objects.create(
        imagen=img,
        motivo=motivo or "Imagen reportada",
        reportado_por=request.user if request.user.is_authenticated else None,
    )
    messages.info(request, "Gracias por avisarnos. Un fiscalizador revisará esta imagen.")
    return redirect("portal:comparar", producto_id=img.producto_id)


@login_required
def vista_servir_imagen_pendiente(request, ruta):
    """
    Sirve imágenes del almacenamiento privado `pendientes/` únicamente al autor o a staff.
    # SEGURIDAD: Evita que imágenes no aprobadas sean accesibles por URL pública o por terceros (IDOR -> 403).
    """
    ruta_norm = f"pendientes/{ruta.lstrip('/')}"
    es_staff = request.user.es_staff_observatorio
    es_autor_foto = ImagenProducto.objects.filter(
        subida_por=request.user, archivo_media=ruta_norm
    ).exists() or ImagenProducto.objects.filter(
        subida_por=request.user, archivo_grande=ruta_norm
    ).exists()
    es_autor_logo = Comercio.objects.filter(
        propietario=request.user, logo=ruta_norm
    ).exists() or Comercio.objects.filter(
        propietario=request.user, logo_miniatura=ruta_norm
    ).exists()

    if not (es_staff or es_autor_foto or es_autor_logo):
        raise PermissionDenied("No tienes permiso para ver esta imagen en revisión.")

    datos = leer_bytes_pendiente(ruta_norm)
    if datos is None:
        raise Http404("Imagen pendiente no encontrada.")

    resp = HttpResponse(datos, content_type="image/webp")
    resp["Cache-Control"] = "private, no-store"
    return resp
