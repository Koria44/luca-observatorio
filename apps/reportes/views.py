"""
Vistas de generación de reportes Excel (`openpyxl`) y PDF (`ReportLab`) (# REQ-14).

Ambas exportaciones consumen la misma función `calcular_indicadores(filtros)` del dashboard
para asegurar coincidencia exacta entre lo mostrado en pantalla y lo descargado.
# SEGURIDAD: Escapa fórmulas peligrosas en celdas Excel (`= + - @`) y registra auditoría EXPORTAR.
"""
from io import BytesIO

from django.core.exceptions import PermissionDenied
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill
from reportlab.graphics.barcode import qr
from reportlab.graphics.shapes import Drawing
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from apps.auditoria.servicios import registrar_auditoria
from apps.comercios.models import Comercio
from apps.nucleo.permisos import comerciante_activo_requerido, solo_fiscalizador_o_admin
from apps.panel.servicios import calcular_indicadores
from apps.precios.models import Precio


def _seguro_excel(valor):
    """Previene inyección de fórmulas en Excel/CSV (# SEGURIDAD / II.11)."""
    if isinstance(valor, str) and valor and valor[0] in ("=", "+", "-", "@"):
        return f"'{valor}"
    return valor


def _extraer_filtros(request) -> dict:
    return {
        "dias": request.GET.get("dias", "30"),
        "categoria": request.GET.get("categoria", ""),
        "sector": request.GET.get("sector", ""),
        "comercio": request.GET.get("comercio", ""),
    }


@solo_fiscalizador_o_admin
def exportar_excel(request):
    """Genera libro Excel (.xlsx) con los indicadores filtrados del observatorio (# REQ-14)."""
    filtros = _extraer_filtros(request)
    datos = calcular_indicadores(filtros)

    wb = Workbook()
    ws = wb.active
    ws.title = "Resumen KPIs"

    estilo_titulo = Font(bold=True, size=14, color="0F2F4D")
    estilo_header = Font(bold=True, color="FFFFFF")
    relleno_marino = PatternFill(start_color="12385C", end_color="12385C", fill_type="solid")

    ws["A1"] = "Luca — Observatorio de Precios del Comercio Local (Pedro Aguirre Cerda)"
    ws["A1"].font = estilo_titulo
    ws["A2"] = f"Fecha de generación: {datos['fecha_generacion']:%d/%m/%Y %H:%M}"
    ws["A3"] = f"Período: {datos['filtros_legibles']['periodo']}"
    ws["A4"] = f"Filtros: Categoría={datos['filtros_legibles']['categoria']} | Sector={datos['filtros_legibles']['sector']} | Comercio={datos['filtros_legibles']['comercio']}"
    ws["A5"] = "Unidades: Pesos chilenos (CLP) | Fuente: Luca PAC (incluye registros DEMO_REFERENCIAL rotulados)"

    ws.append([])
    ws.append(["Indicador", "Valor"])
    for cell in ws[7]:
        cell.font = estilo_header
        cell.fill = relleno_marino

    k = datos["kpis"]
    filas_kpi = [
        ("Canasta básica promedio (CLP)", k["canasta_prom"]),
        ("Canasta básica mínima (CLP)", k["canasta_min"]),
        ("Canasta básica máxima (CLP)", k["canasta_max"]),
        ("Ítems canasta básica considerados", k["canasta_items"]),
        ("Precio promedio general (CLP)", k["precio_promedio"]),
        ("Precio mínimo observado (CLP)", k["precio_minimo"]),
        ("Precio máximo observado (CLP)", k["precio_maximo"]),
        ("Ofertas vigentes", k["ofertas_vigentes"]),
        ("Productos monitoreados", k["productos_monitoreados"]),
        ("Comercios / sucursales activas", k["comercios_activos"]),
        ("Cobertura de sectores PAC (%)", k["cobertura_sectores_pct"]),
        ("Antigüedad promedio del dato (días)", k["antiguedad_promedio_dias"]),
    ]
    for etiq, val in filas_kpi:
        ws.append([_seguro_excel(etiq), _seguro_excel(val)])

    # Hoja 2: Por categoría
    ws_cat = wb.create_sheet("Por Categoría")
    ws_cat.append(["Categoría", "Precio promedio (CLP)", "Mínimo (CLP)", "Máximo (CLP)", "Registros"])
    for cell in ws_cat[1]:
        cell.font = estilo_header
        cell.fill = relleno_marino
    for c in datos["por_categoria"]:
        ws_cat.append([
            _seguro_excel(c["etiqueta"]),
            c["promedio"],
            c["minimo"],
            c["maximo"],
            c["cantidad"],
        ])

    # Hoja 3: Por comercio
    ws_com = wb.create_sheet("Por Comercio")
    ws_com.append(["Comercio", "Precio promedio observado (CLP)", "Cantidad de registros"])
    for cell in ws_com[1]:
        cell.font = estilo_header
        cell.fill = relleno_marino
    for co in datos["por_comercio"]:
        ws_com.append([_seguro_excel(co["etiqueta"]), co["valor"], co["cantidad"]])

    buffer = BytesIO()
    wb.save(buffer)
    buffer.seek(0)

    registrar_auditoria(
        usuario=request.user,
        accion="EXPORTAR",
        modelo="ReporteExcel",
        valores_nuevos={"filtros": filtros, "ofertas_vigentes": k["ofertas_vigentes"]},
        request=request,
    )

    resp = HttpResponse(
        buffer.getvalue(),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    resp["Content-Disposition"] = 'attachment; filename="reporte_observatorio_luca_pac.xlsx"'
    return resp


@solo_fiscalizador_o_admin
def exportar_pdf(request):
    """Genera informe PDF institucional con ReportLab respetando los filtros activos (# REQ-14)."""
    filtros = _extraer_filtros(request)
    datos = calcular_indicadores(filtros)

    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, title="Reporte Observatorio Luca PAC")
    styles = getSampleStyleSheet()
    elementos = []

    elementos.append(Paragraph("<b>Luca — Observatorio de Precios del Comercio Local (Pedro Aguirre Cerda)</b>", styles["Title"]))
    elementos.append(Spacer(1, 6))
    elementos.append(Paragraph(f"<b>Fecha de generación:</b> {datos['fecha_generacion']:%d/%m/%Y %H:%M}", styles["Normal"]))
    elementos.append(Paragraph(f"<b>Período:</b> {datos['filtros_legibles']['periodo']}", styles["Normal"]))
    elementos.append(
        Paragraph(
            f"<b>Filtros:</b> Categoría: {datos['filtros_legibles']['categoria']} · "
            f"Sector: {datos['filtros_legibles']['sector']} · Comercio: {datos['filtros_legibles']['comercio']}",
            styles["Normal"],
        )
    )
    elementos.append(Paragraph("<b>Unidades:</b> Pesos chilenos (CLP) · <b>Fuente:</b> Observatorio Luca PAC (proyecto académico TIHI43)", styles["Normal"]))
    elementos.append(Spacer(1, 14))

    k = datos["kpis"]
    elementos.append(Paragraph("<b>1. Indicadores principales</b>", styles["Heading2"]))
    tabla_kpi = Table(
        [
            ["Indicador", "Valor"],
            ["Canasta básica promedio (CLP)", f"${k['canasta_prom']:,}"],
            ["Canasta básica mínima / máxima (CLP)", f"${k['canasta_min']:,} / ${k['canasta_max']:,}"],
            ["Precio promedio general (CLP)", f"${k['precio_promedio']:,}"],
            ["Ofertas vigentes", str(k["ofertas_vigentes"])],
            ["Productos monitoreados", str(k["productos_monitoreados"])],
            ["Comercios activos / Cobertura PAC", f"{k['comercios_activos']} locales ({k['cobertura_sectores_pct']}%)"],
        ],
        colWidths=[280, 200],
    )
    tabla_kpi.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#12385C")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#D9E2EC")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#FFFBF2")]),
                ("PADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    elementos.append(tabla_kpi)
    elementos.append(Spacer(1, 14))

    elementos.append(Paragraph("<b>2. Resumen por categoría (CLP)</b>", styles["Heading2"]))
    filas_cat = [["Categoría", "Promedio", "Mínimo", "Máximo", "Muestras"]]
    for c in datos["por_categoria"]:
        filas_cat.append([c["etiqueta"], f"${c['promedio']:,}", f"${c['minimo']:,}", f"${c['maximo']:,}", str(c["cantidad"])])
    tabla_cat = Table(filas_cat, colWidths=[170, 85, 80, 80, 65])
    tabla_cat.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0B6E70")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#D9E2EC")),
                ("PADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    elementos.append(tabla_cat)
    elementos.append(Spacer(1, 16))
    elementos.append(
        Paragraph(
            "<i>Nota: Proyecto académico (TIHI43). No es un documento oficial de la Municipalidad de Pedro Aguirre Cerda.</i>",
            styles["Normal"],
        )
    )

    doc.build(elementos)
    buffer.seek(0)

    registrar_auditoria(
        usuario=request.user,
        accion="EXPORTAR",
        modelo="ReportePDF",
        valores_nuevos={"filtros": filtros, "ofertas_vigentes": k["ofertas_vigentes"]},
        request=request,
    )

    resp = HttpResponse(buffer.getvalue(), content_type="application/pdf")
    resp["Content-Disposition"] = 'attachment; filename="reporte_observatorio_luca_pac.pdf"'
    return resp


@comerciante_activo_requerido
def exportar_afiche_qr(request, comercio_id):
    """
    Genera un afiche imprimible PDF con Sello 'Comercio Verificado y Transparente' y código QR
    que enlaza directo a la ficha pública de precios del local.
    """
    comercio = get_object_or_404(Comercio, pk=comercio_id)
    es_staff = request.user.es_staff_observatorio
    if not es_staff and comercio.propietario_id != request.user.id:
        raise PermissionDenied("Solo puedes descargar el afiche QR de tu propio comercio.")

    sucursal = comercio.sucursales.filter(activa=True).first()
    ruta_publica = f"/comercio/{sucursal.id}/" if sucursal else "/mapa/"
    url_destino = request.build_absolute_uri(ruta_publica)

    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, title=f"Afiche QR — {comercio.nombre_fantasia}")
    styles = getSampleStyleSheet()
    elementos = []

    elementos.append(Paragraph("<b>LUCA — OBSERVATORIO DE PRECIOS · PEDRO AGUIRRE CERDA</b>", styles["Title"]))
    elementos.append(Spacer(1, 10))
    elementos.append(Paragraph("<b>COMERCIO VERIFICADO Y TRANSPARENTE</b>", styles["Heading2"]))
    elementos.append(Spacer(1, 8))
    elementos.append(Paragraph(f"<font size=18><b>{comercio.nombre_fantasia}</b></font>", styles["Normal"]))
    if sucursal:
        elementos.append(Spacer(1, 6))
        elementos.append(Paragraph(f"Dirección: {sucursal.direccion} · Sector {sucursal.sector}", styles["Normal"]))
    elementos.append(Spacer(1, 18))

    # Código QR nativo de ReportLab
    qr_widget = qr.QrCodeWidget(url_destino)
    bounds = qr_widget.getBounds()
    w = bounds[2] - bounds[0]
    h = bounds[3] - bounds[1]
    dibujo = Drawing(210, 210, transform=[210.0 / w, 0, 0, 210.0 / h, 0, 0])
    dibujo.add(qr_widget)
    elementos.append(dibujo)
    elementos.append(Spacer(1, 14))

    elementos.append(Paragraph("<b>Escanea este código QR con tu celular para ver nuestros precios vigentes y ofertas.</b>", styles["Heading3"]))
    elementos.append(Paragraph(f"Enlace directo: {url_destino}", styles["Normal"]))
    elementos.append(Spacer(1, 18))
    elementos.append(Paragraph("<i>Cada luca cuenta · Proyecto académico TIHI43 (No es un sello oficial municipal).</i>", styles["Normal"]))

    doc.build(elementos)
    buffer.seek(0)

    registrar_auditoria(
        usuario=request.user,
        accion="EXPORTAR",
        modelo="AficheQR",
        objeto_id=str(comercio.pk),
        valores_nuevos={"url_qr": url_destino},
        request=request,
    )

    resp = HttpResponse(buffer.getvalue(), content_type="application/pdf")
    resp["Content-Disposition"] = f'attachment; filename="afiche_qr_luca_{comercio.id}.pdf"'
    return resp


@solo_fiscalizador_o_admin
def exportar_boletin_semanal(request):
    """Genera el Boletín Semanal PDF de la Canasta Básica de Pedro Aguirre Cerda."""
    datos = calcular_indicadores({"dias": "7"})
    k = datos["kpis"]

    variaciones = list(
        Precio.objects.vigentes()
        .filter(variacion_porcentual__isnull=False)
        .select_related("producto", "producto__marca", "sucursal", "sucursal__comercio")
    )
    top_bajas = sorted([p for p in variaciones if p.variacion_porcentual < 0], key=lambda p: p.variacion_porcentual)[:5]
    top_alzas = sorted([p for p in variaciones if p.variacion_porcentual > 0], key=lambda p: p.variacion_porcentual, reverse=True)[:5]
    ofertas_top = sorted(
        list(Precio.objects.ofertas_vigentes().select_related("producto", "producto__marca", "sucursal", "sucursal__comercio")[:20]),
        key=lambda p: p.porcentaje_descuento,
        reverse=True,
    )[:5]

    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, title="Boletín Semanal Canasta Básica PAC")
    styles = getSampleStyleSheet()
    elementos = []

    elementos.append(Paragraph("<b>Boletín Semanal de Precios — Pedro Aguirre Cerda</b>", styles["Title"]))
    elementos.append(Paragraph(f"<b>Generado:</b> {datos['fecha_generacion']:%d/%m/%Y %H:%M} · <b>Período:</b> {datos['filtros_legibles']['periodo']}", styles["Normal"]))
    elementos.append(Spacer(1, 12))

    elementos.append(Paragraph("<b>1. Costo de la Canasta Básica Local</b>", styles["Heading2"]))
    elementos.append(
        Paragraph(
            f"Promedio comunal: <b>${k['canasta_prom']:,}</b> · Opción más económica: <b>${k['canasta_min']:,}</b> · "
            f"Opción más cara: <b>${k['canasta_max']:,}</b> (Ahorro potencial: <b>${max(0, k['canasta_max'] - k['canasta_min']):,}</b>).",
            styles["Normal"],
        )
    )
    elementos.append(Spacer(1, 10))

    elementos.append(Paragraph("<b>2. Top 5 mayores bajas de la semana</b>", styles["Heading2"]))
    filas_bajas = [["Producto", "Comercio", "Precio", "Variación"]]
    for p in top_bajas:
        filas_bajas.append([p.producto.nombre_completo[:42], p.sucursal.nombre_visible[:28], f"${p.precio_vigente:,}", f"{p.variacion_porcentual}%"])
    if len(filas_bajas) == 1:
        filas_bajas.append(["Sin bajas registradas en los últimos 7 días", "—", "—", "—"])
    t_bajas = Table(filas_bajas, colWidths=[200, 145, 70, 65])
    t_bajas.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#187540")), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white), ("GRID", (0, 0), (-1, -1), 0.5, colors.grey), ("PADDING", (0, 0), (-1, -1), 5)]))
    elementos.append(t_bajas)
    elementos.append(Spacer(1, 10))

    elementos.append(Paragraph("<b>3. Top 5 mayores alzas de la semana</b>", styles["Heading2"]))
    filas_alzas = [["Producto", "Comercio", "Precio", "Variación"]]
    for p in top_alzas:
        filas_alzas.append([p.producto.nombre_completo[:42], p.sucursal.nombre_visible[:28], f"${p.precio_vigente:,}", f"+{p.variacion_porcentual}%"])
    if len(filas_alzas) == 1:
        filas_alzas.append(["Sin alzas registradas en los últimos 7 días", "—", "—", "—"])
    t_alzas = Table(filas_alzas, colWidths=[200, 145, 70, 65])
    t_alzas.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#C62828")), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white), ("GRID", (0, 0), (-1, -1), 0.5, colors.grey), ("PADDING", (0, 0), (-1, -1), 5)]))
    elementos.append(t_alzas)
    elementos.append(Spacer(1, 10))

    elementos.append(Paragraph("<b>4. Mejores ofertas vigentes para vecinos</b>", styles["Heading2"]))
    filas_of = [["Producto", "Comercio", "Oferta", "Descuento"]]
    for p in ofertas_top:
        filas_of.append([p.producto.nombre_completo[:42], p.sucursal.nombre_visible[:28], f"${p.precio_oferta:,}", f"-{p.porcentaje_descuento}%"])
    t_of = Table(filas_of, colWidths=[200, 145, 70, 65])
    t_of.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#12385C")), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white), ("GRID", (0, 0), (-1, -1), 0.5, colors.grey), ("PADDING", (0, 0), (-1, -1), 5)]))
    elementos.append(t_of)
    elementos.append(Spacer(1, 14))
    elementos.append(Paragraph("<i>Boletín comunitario Luca PAC · Proyecto académico TIHI43.</i>", styles["Normal"]))

    doc.build(elementos)
    buffer.seek(0)

    registrar_auditoria(
        usuario=request.user,
        accion="EXPORTAR",
        modelo="BoletinSemanalPDF",
        valores_nuevos={"canasta_prom": k["canasta_prom"]},
        request=request,
    )
    resp = HttpResponse(buffer.getvalue(), content_type="application/pdf")
    resp["Content-Disposition"] = 'attachment; filename="boletin_semanal_luca_pac.pdf"'
    return resp
