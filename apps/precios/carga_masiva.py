"""
Carga masiva de precios desde CSV o Excel (.xlsx) con vista previa, validación por fila,
informe de errores y confirmación respetando permisos y flujo de aprobación (# REQ-10).

# SEGURIDAD / II.11:
- Extensión y tipo validados (.csv, .xlsx únicamente).
- Límite estricto de tamaño <= 2 MB y <= 2.000 filas (compatible con Vercel).
- Verificación de propiedad de sucursal en cada fila si el usuario es COMERCIANTE.
"""
import csv
from datetime import date
from io import BytesIO, StringIO

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from openpyxl import load_workbook

from apps.auditoria.servicios import registrar_auditoria
from apps.catalogo.models import Producto
from apps.comercios.models import Sucursal
from apps.nucleo.permisos import rol_requerido

from .models import CargaMasiva, Precio
from .servicios import registrar_o_actualizar_precio

MAX_BYTES = 2 * 1024 * 1024  # 2 MB
MAX_FILAS = 2000
COLUMNAS_OBLIGATORIAS = {"producto_id", "sucursal_id", "precio_normal"}


def _leer_filas_archivo(archivo) -> tuple[list[str], list[dict]]:
    """Lee un archivo CSV o XLSX y devuelve `(encabezados, filas_dict)`."""
    nombre = (archivo.name or "").lower()
    if archivo.size > MAX_BYTES:
        raise ValidationError("El archivo supera el tamaño máximo permitido de 2 MB.")

    if nombre.endswith(".csv"):
        contenido = archivo.read().decode("utf-8-sig")
        lector = csv.DictReader(StringIO(contenido))
        encabezados = [c.strip().lower() for c in (lector.fieldnames or [])]
        filas = []
        for idx, fila in enumerate(lector, start=2):
            if idx - 1 > MAX_FILAS:
                raise ValidationError(f"El archivo supera el límite de {MAX_FILAS} filas por carga.")
            filas.append({(k or "").strip().lower(): (v or "").strip() for k, v in fila.items()})
        return encabezados, filas

    if nombre.endswith(".xlsx"):
        wb = load_workbook(BytesIO(archivo.read()), read_only=True, data_only=True)
        ws = wb.active
        iter_rows = ws.iter_rows(values_only=True)
        primera = next(iter_rows, None)
        if not primera:
            raise ValidationError("El archivo Excel está vacío.")
        encabezados = [str(c or "").strip().lower() for c in primera]
        filas = []
        for idx, row in enumerate(iter_rows, start=2):
            if idx - 1 > MAX_FILAS:
                raise ValidationError(f"El archivo supera el límite de {MAX_FILAS} filas por carga.")
            if all(v is None or str(v).strip() == "" for v in row):
                continue
            filas.append({encabezados[i]: ("" if row[i] is None else str(row[i]).strip()) for i in range(min(len(encabezados), len(row)))})
        return encabezados, filas

    raise ValidationError("Formato no permitido. Sube un archivo .csv o .xlsx.")


def _validar_filas(filas: list[dict], usuario) -> tuple[list[dict], list[dict]]:
    """Valida fila por fila y devuelve `(filas_validas, errores)`."""
    validas = []
    errores = []
    es_comerciante = usuario.rol == "COMERCIANTE"

    for num_fila, fila in enumerate(filas, start=2):
        # 1. Producto
        prod_id = fila.get("producto_id", "")
        if not prod_id.isdigit():
            errores.append({"fila": num_fila, "columna": "producto_id", "mensaje": "Debe ser un ID numérico de producto."})
            continue
        producto = Producto.objects.filter(pk=int(prod_id), activo=True).first()
        if not producto:
            errores.append({"fila": num_fila, "columna": "producto_id", "mensaje": f"No existe producto activo #{prod_id}."})
            continue

        # 2. Sucursal y permiso de propiedad (# SEGURIDAD / IDOR)
        suc_id = fila.get("sucursal_id", "")
        if not suc_id.isdigit():
            errores.append({"fila": num_fila, "columna": "sucursal_id", "mensaje": "Debe ser un ID numérico de sucursal."})
            continue
        sucursal = Sucursal.objects.select_related("comercio").filter(pk=int(suc_id), activa=True).first()
        if not sucursal:
            errores.append({"fila": num_fila, "columna": "sucursal_id", "mensaje": f"No existe sucursal activa #{suc_id}."})
            continue
        if es_comerciante and sucursal.comercio.propietario_id != usuario.id:
            errores.append({"fila": num_fila, "columna": "sucursal_id", "mensaje": "No tienes permiso para cargar precios en una sucursal ajena."})
            continue

        # 3. Precios
        try:
            p_normal = int(float(fila.get("precio_normal", "")))
            if p_normal <= 0:
                raise ValueError()
        except ValueError:
            errores.append({"fila": num_fila, "columna": "precio_normal", "mensaje": "Precio normal debe ser un entero mayor a 0."})
            continue

        p_oferta = None
        if fila.get("precio_oferta"):
            try:
                p_oferta = int(float(fila["precio_oferta"]))
                if p_oferta <= 0 or p_oferta >= p_normal:
                    errores.append({"fila": num_fila, "columna": "precio_oferta", "mensaje": "El precio de oferta debe ser positivo y menor al normal."})
                    continue
            except ValueError:
                errores.append({"fila": num_fila, "columna": "precio_oferta", "mensaje": "Precio de oferta inválido."})
                continue

        # 4. Fechas
        vig_desde = timezone.localdate()
        vig_hasta = None
        try:
            if fila.get("vigencia_desde"):
                vig_desde = date.fromisoformat(fila["vigencia_desde"][:10])
            if fila.get("vigencia_hasta"):
                vig_hasta = date.fromisoformat(fila["vigencia_hasta"][:10])
            if vig_hasta and vig_hasta < vig_desde:
                errores.append({"fila": num_fila, "columna": "vigencia_hasta", "mensaje": "vigencia_hasta no puede ser anterior a vigencia_desde."})
                continue
        except ValueError:
            errores.append({"fila": num_fila, "columna": "vigencia_desde/hasta", "mensaje": "Usa formato de fecha AAAA-MM-DD."})
            continue

        validas.append(
            {
                "fila": num_fila,
                "producto_id": producto.id,
                "producto_nombre": producto.nombre_completo,
                "sucursal_id": sucursal.id,
                "sucursal_nombre": sucursal.nombre_visible,
                "precio_normal": p_normal,
                "precio_oferta": p_oferta,
                "vigencia_desde": vig_desde.isoformat(),
                "vigencia_hasta": vig_hasta.isoformat() if vig_hasta else None,
                "condiciones": fila.get("condiciones", "")[:200],
            }
        )
    return validas, errores


@rol_requerido("COMERCIANTE", "FISCALIZADOR", "ADMIN")
def descargar_plantilla_carga(request):
    """Descarga una plantilla CSV lista para completar e importar (# REQ-10)."""
    resp = HttpResponse(content_type="text/csv; charset=utf-8")
    resp["Content-Disposition"] = 'attachment; filename="plantilla_carga_precios_luca.csv"'
    resp.write("\ufeff")
    writer = csv.writer(resp)
    writer.writerow(["producto_id", "sucursal_id", "precio_normal", "precio_oferta", "vigencia_desde", "vigencia_hasta", "condiciones"])
    prod = Producto.objects.first()
    suc = (
        Sucursal.objects.filter(comercio__propietario=request.user).first()
        if request.user.rol == "COMERCIANTE"
        else Sucursal.objects.first()
    )
    if prod and suc:
        hoy = timezone.localdate().isoformat()
        writer.writerow([prod.id, suc.id, 1590, 1390, hoy, "", "Oferta de ejemplo"])
    return resp


@rol_requerido("COMERCIANTE", "FISCALIZADOR", "ADMIN")
def vista_carga_masiva(request):
    """Flujo en dos pasos: 1) Subir y validar con vista previa; 2) Confirmar filas válidas (# REQ-10)."""
    contexto = {
        "historial_cargas": CargaMasiva.objects.filter(usuario=request.user)[:10],
        "vista_previa": None,
        "errores": [],
        "carga_id": None,
    }

    if request.method == "POST":
        paso = request.POST.get("paso", "validar")

        if paso == "validar":
            archivo = request.FILES.get("archivo")
            if not archivo:
                messages.error(request, "Selecciona un archivo .csv o .xlsx para validar.")
                return render(request, "precios/carga_masiva.html", contexto)
            try:
                encabezados, filas = _leer_filas_archivo(archivo)
                faltantes = COLUMNAS_OBLIGATORIAS - set(encabezados)
                if faltantes:
                    raise ValidationError(f"Faltan columnas obligatorias: {', '.join(sorted(faltantes))}.")
                validas, errores = _validar_filas(filas, request.user)
            except ValidationError as exc:
                messages.error(request, exc.message)
                return render(request, "precios/carga_masiva.html", contexto)

            carga = CargaMasiva.objects.create(
                usuario=request.user,
                nombre_archivo=archivo.name[:255],
                estado=CargaMasiva.Estado.VALIDADA if validas else CargaMasiva.Estado.CON_ERRORES,
                filas_total=len(filas),
                filas_ok=len(validas),
                filas_error=len(errores),
                informe_errores=errores,
            )
            request.session["carga_masiva_pendiente"] = {"carga_id": carga.id, "validas": validas}
            contexto.update({"vista_previa": validas, "errores": errores, "carga_id": carga.id})
            return render(request, "precios/carga_masiva.html", contexto)

        if paso == "confirmar":
            pendiente = request.session.pop("carga_masiva_pendiente", None)
            if not pendiente or not pendiente.get("validas"):
                messages.warning(request, "No hay una vista previa válida lista para confirmar.")
                return redirect("precios:carga_masiva")

            carga = CargaMasiva.objects.filter(pk=pendiente["carga_id"], usuario=request.user).first()
            importados = 0
            errores_conf = []
            for item in pendiente["validas"]:
                prod = Producto.objects.get(pk=item["producto_id"])
                suc = Sucursal.objects.select_related("comercio").get(pk=item["sucursal_id"])
                try:
                    registrar_o_actualizar_precio(
                        producto=prod,
                        sucursal=suc,
                        precio_normal=item["precio_normal"],
                        precio_oferta=item["precio_oferta"],
                        vigencia_desde=date.fromisoformat(item["vigencia_desde"]),
                        vigencia_hasta=date.fromisoformat(item["vigencia_hasta"]) if item["vigencia_hasta"] else None,
                        condiciones=item["condiciones"],
                        fuente=Precio.Fuente.CARGA_MASIVA,
                        fuente_detalle=f"Carga masiva #{pendiente['carga_id']}",
                        registrado_por=request.user,
                        request=request,
                    )
                    importados += 1
                except ValidationError as exc:
                    errores_conf.append({"fila": item["fila"], "columna": "registro", "mensaje": str(exc.message)})

            if carga:
                carga.estado = CargaMasiva.Estado.CONFIRMADA
                carga.filas_ok = importados
                if errores_conf:
                    carga.informe_errores = list(carga.informe_errores) + errores_conf
                    carga.filas_error = len(carga.informe_errores)
                carga.save()

            registrar_auditoria(
                usuario=request.user,
                accion="CARGA",
                modelo="CargaMasiva",
                objeto_id=str(pendiente["carga_id"]),
                valores_nuevos={"importados": importados, "errores": len(errores_conf)},
                request=request,
            )
            messages.success(request, f"Carga masiva completada: {importados} precio(s) importado(s) respetando el flujo de validación.")
            return redirect("precios:carga_masiva")

    return render(request, "precios/carga_masiva.html", contexto)
