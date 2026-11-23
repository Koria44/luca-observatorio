"""
Servicios de Productos Genéricos, equivalencias entre marcas, cálculo de mediana de referencia
y tratamiento prudente de medicamentos de venta directa (# Prompt 7 Sección 6).
"""
from decimal import Decimal
from statistics import median

from apps.catalogo.models import Producto, ProductoGenerico
from apps.precios.models import Precio

AVISO_MEDICAMENTO_REFERENCIAL = (
    "Esta información es solo referencial de precios para productos de venta directa; "
    "no constituye consejo médico. Consulte siempre a un químico farmacéutico o a su médico."
)


def _unidad_base_de(unidad_medida: str) -> str:
    if unidad_medida in ("g", "kg"):
        return ProductoGenerico.UnidadBase.GRAMO
    if unidad_medida in ("ml", "l"):
        return ProductoGenerico.UnidadBase.MILILITRO
    return ProductoGenerico.UnidadBase.UNIDAD


def poblar_genericos_desde_catalogo() -> dict:
    """
    Asigna de forma idempotente los productos existentes a fichas canónicas `ProductoGenerico`
    agrupando por `(categoria, nombre, unidad_base, contenido_base)` (# Sección 6.3).
    """
    creados = 0
    vinculados = 0
    for prod in Producto.objects.filter(activo=True).select_related("categoria", "marca"):
        ubase = _unidad_base_de(prod.unidad_medida)
        nombre_canon = f"{prod.nombre} · {prod.contenido_legible}"
        es_granel = prod.marca.nombre in ("Feria PAC", "Lo Valledor", "Elaboración Propia", "Panadería Local", "Granja PAC")
        gen, creado = ProductoGenerico.objects.get_or_create(
            nombre=nombre_canon,
            defaults={
                "categoria": prod.categoria,
                "unidad_base": ubase,
                "contenido_base": prod.contenido_base,
                "tolerancia_pct": 5,
                "es_canasta_basica": prod.es_canasta_basica,
                "es_a_granel": es_granel,
                "activo": True,
            },
        )
        if creado:
            creados += 1

        cambios = []
        if prod.generico_id != gen.id:
            prod.generico = gen
            cambios.append("generico")
        if es_granel and prod.tipo_marca != Producto.TipoMarca.GENERICO_SIN_MARCA:
            prod.tipo_marca = Producto.TipoMarca.GENERICO_SIN_MARCA
            cambios.append("tipo_marca")
        elif prod.marca.nombre == "Lider" and prod.tipo_marca != Producto.TipoMarca.MARCA_PROPIA:
            prod.tipo_marca = Producto.TipoMarca.MARCA_PROPIA
            cambios.append("tipo_marca")
        if prod.categoria.slug == "farmacia-venta-libre" and not prod.es_medicamento_venta_directa:
            prod.es_medicamento_venta_directa = True
            prod.es_bioequivalente_certificado = Producto.EstadoBioequivalencia.NO_VERIFICADO
            cambios.extend(["es_medicamento_venta_directa", "es_bioequivalente_certificado"])

        if cambios:
            prod.save(update_fields=cambios)
            vinculados += 1

    total = Producto.objects.filter(activo=True).count()
    con_gen = Producto.objects.filter(activo=True, generico__isnull=False).count()
    return {
        "genericos_creados": creados,
        "productos_vinculados": vinculados,
        "total_productos": total,
        "con_generico": con_gen,
        "sin_generico": total - con_gen,
    }


def obtener_equivalentes_y_mediana(producto: Producto) -> dict:
    """
    Devuelve los precios vigentes de todos los productos equivalentes (mismo `ProductoGenerico`
    dentro de tolerancia ±5 %) ordenados por precio por unidad, y la mediana de referencia (# Sección 6.4).
    """
    if not producto.generico_id:
        return {"equivalentes": [], "mediana_unidad": None, "mas_barato_equivalente": None}

    prods_eq = list(producto.generico.productos_equivalentes())
    ids_eq = [p.id for p in prods_eq]
    precios = list(
        Precio.objects.vigentes()
        .filter(producto_id__in=ids_eq)
        .select_related("producto", "producto__marca", "sucursal", "sucursal__comercio")
    )
    precios.sort(key=lambda pr: (pr.precio_por_unidad, pr.precio_vigente))
    valores_unidad = [pr.precio_por_unidad for pr in precios if pr.precio_por_unidad > 0]
    mediana_u = int(round(median(valores_unidad))) if valores_unidad else None
    return {
        "equivalentes": precios[:12],
        "mediana_unidad": mediana_u,
        "mas_barato_equivalente": precios[0] if precios else None,
    }
