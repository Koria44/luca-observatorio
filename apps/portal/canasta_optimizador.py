"""
Motor de optimización y comparación producto por producto para Mi Lista de Compras.
Calcula:
- Análisis por producto: mejor local, 2.ª opción con diferencia, más caro, promedio y avisos.
- Escenarios de ruta: 1 local, 2 locales, 3 locales y Ahorro máximo (sin límite de paradas).
- Regla de umbral de ahorro por desvío para recomendar la ruta más conveniente.
"""
from collections import defaultdict
from itertools import combinations

from apps.catalogo.models import Producto
from apps.precios.models import Precio


def _clave_precio(precio_obj, sector_preferido: str = ""):
    """Orden determinista de ofertas: menor precio, sector preferido, fecha más reciente."""
    pref = 0 if (sector_preferido and precio_obj.sucursal.sector == sector_preferido) else 1
    fecha_ord = precio_obj.fecha_observacion.toordinal() if precio_obj.fecha_observacion else 0
    return (precio_obj.precio_vigente, pref, -fecha_ord, precio_obj.sucursal_id)


def _evaluar_escenario(
    escenario_id: str,
    titulo: str,
    sids: list[int],
    productos: dict[int, Producto],
    cantidades: dict[int, int],
    matriz: dict[int, dict[int, Precio]],
    sucursales_info: dict[int, object],
    sector_preferido: str,
    mejor_global_por_prod: dict[int, Precio],
    mas_caro_por_prod: dict[int, Precio],
) -> dict:
    """Asigna cada producto al local más barato dentro de `sids` y arma el desglose completo."""
    # Conteo preliminar de cobertura para desempatar precios iguales hacia el local con más ítems
    cobertura_sid = {sid: sum(1 for pid in productos if pid in matriz[sid]) for sid in sids}

    asignados_por_sid = defaultdict(list)
    faltantes = []
    total_clp = 0
    cubiertos = 0

    for pid, prod in productos.items():
        candidatos = []
        for sid in sids:
            pr = matriz[sid].get(pid)
            if pr is not None:
                candidatos.append(pr)
        if not candidatos:
            faltantes.append({"producto_id": pid, "nombre": prod.nombre_completo, "cantidad": cantidades[pid]})
            continue

        # Elegir el más barato dentro del conjunto; en empate preferir el local con más cobertura
        candidatos.sort(
            key=lambda pr: (
                pr.precio_vigente,
                -cobertura_sid.get(pr.sucursal_id, 0),
                0 if (sector_preferido and pr.sucursal.sector == sector_preferido) else 1,
                -(pr.fecha_observacion.toordinal() if pr.fecha_observacion else 0),
                pr.sucursal_id,
            )
        )
        elegido = candidatos[0]
        cant = cantidades[pid]
        subtotal = elegido.precio_vigente * cant
        total_clp += subtotal
        cubiertos += 1

        mejor_global = mejor_global_por_prod.get(pid)
        mas_caro = mas_caro_por_prod.get(pid)
        es_mejor_global = bool(mejor_global and elegido.precio_vigente <= mejor_global.precio_vigente)
        dif_mejor_global = 0
        mejor_otro_local = None
        if mejor_global and elegido.precio_vigente > mejor_global.precio_vigente:
            dif_mejor_global = (elegido.precio_vigente - mejor_global.precio_vigente) * cant
            mejor_otro_local = {
                "local": mejor_global.sucursal.nombre_visible,
                "sector": mejor_global.sucursal.sector,
                "precio_unitario": mejor_global.precio_vigente,
                "diferencia_subtotal": dif_mejor_global,
            }

        ahorro_vs_caro = max(0, (mas_caro.precio_vigente - elegido.precio_vigente) * cant) if mas_caro else 0
        condiciones = list(elegido.etiquetas_condiciones)
        aviso_limite = bool(elegido.compra_minima and cant < elegido.compra_minima)

        asignados_por_sid[elegido.sucursal_id].append(
            {
                "producto_id": pid,
                "producto": prod.nombre_completo,
                "cantidad": cant,
                "precio_unitario": elegido.precio_vigente,
                "subtotal": subtotal,
                "es_oferta": elegido.es_oferta_activa,
                "condiciones": condiciones,
                "aviso_condicion": aviso_limite or bool(condiciones),
                "es_mejor_global": es_mejor_global,
                "mejor_otro_local": mejor_otro_local,
                "ahorro_vs_caro": ahorro_vs_caro,
            }
        )

    locales = []
    for sid, lista_items in asignados_por_sid.items():
        suc = sucursales_info[sid]
        lista_items.sort(key=lambda x: (-x["subtotal"], x["producto"]))
        sub_local = sum(x["subtotal"] for x in lista_items)
        ahorro_local = sum(x["ahorro_vs_caro"] for x in lista_items)
        locales.append(
            {
                "sucursal_id": sid,
                "nombre": suc.nombre_visible,
                "direccion": suc.direccion,
                "sector": suc.sector,
                "url": f"/comercio/{sid}/",
                "maps_url": f"https://www.google.com/maps/dir/?api=1&destination={suc.latitud},{suc.longitud}",
                "subtotal_clp": sub_local,
                "ahorro_vs_caro_clp": ahorro_local,
                "cantidad_items": len(lista_items),
                "items": lista_items,
            }
        )
    locales.sort(key=lambda loc: (-loc["cantidad_items"], -loc["subtotal_clp"]))

    total_solicitados = len(productos)
    return {
        "id": escenario_id,
        "titulo": titulo,
        "cubiertos": cubiertos,
        "total_solicitados": total_solicitados,
        "completo": cubiertos == total_solicitados,
        "total_clp": total_clp,
        "paradas": len(locales),
        "ahorro_vs_uno": 0,
        "recomendado": False,
        "locales": locales,
        "faltantes": faltantes,
    }


def calcular_optimizacion_canasta(
    items: list[dict],
    umbral_desvio: int = 500,
    max_locales: int = 3,
    sector_preferido: str = "",
) -> dict:
    """
    Optimiza la lista de compras del vecino comparando producto por producto y
    evaluando rutas de 1, 2, 3 locales y Ahorro máximo (sin límite de paradas).
    """
    # SEGURIDAD: Validar y acotar parámetros numéricos en el servidor
    try:
        umbral_desvio = max(0, min(10000, int(umbral_desvio)))
    except (TypeError, ValueError):
        umbral_desvio = 500
    try:
        max_locales = max(1, min(10, int(max_locales)))
    except (TypeError, ValueError):
        max_locales = 3
    sector_preferido = (sector_preferido or "").strip()

    cantidades = {}
    for it in items[:30]:
        try:
            pid = int(it["producto_id"])
            cant = max(1, min(20, int(it.get("cantidad", 1))))
            cantidades[pid] = cant
        except (KeyError, TypeError, ValueError):
            continue

    vacio = {
        "items_detalle": [],
        "analisis_productos": [],
        "sin_precio": [],
        "escenarios": [],
        "escenario_recomendado_id": None,
        "configuracion": {"umbral_desvio": umbral_desvio, "max_locales": max_locales},
        # Claves heredadas por compatibilidad
        "mejor_unico": None,
        "ranking_unicos": [],
        "mejor_combinacion_dos": None,
        "ahorro_vs_max": 0,
    }
    if not cantidades:
        return vacio

    productos = {
        p.id: p
        for p in Producto.objects.filter(id__in=cantidades.keys(), activo=True).select_related("marca", "categoria")
    }
    if not productos:
        return vacio

    precios_vig = list(
        Precio.objects.vigentes()
        .filter(producto_id__in=productos.keys())
        .select_related("sucursal", "sucursal__comercio")
    )

    # Matriz: sucursal_id -> {producto_id: Precio más barato vigente}
    matriz: dict[int, dict[int, Precio]] = defaultdict(dict)
    por_producto: dict[int, list[Precio]] = defaultdict(list)
    sucursales_info: dict[int, object] = {}

    for pr in precios_vig:
        sid = pr.sucursal_id
        sucursales_info[sid] = pr.sucursal
        actual = matriz[sid].get(pr.producto_id)
        if actual is None or _clave_precio(pr, sector_preferido) < _clave_precio(actual, sector_preferido):
            matriz[sid][pr.producto_id] = pr

    for sid, mapa_p in matriz.items():
        for pid, pr in mapa_p.items():
            por_producto[pid].append(pr)

    # 1. Análisis producto por producto
    analisis_productos = []
    sin_precio = []
    mejor_global_por_prod: dict[int, Precio] = {}
    mas_caro_por_prod: dict[int, Precio] = {}

    for pid, prod in productos.items():
        cant = cantidades[pid]
        ofertas = sorted(por_producto.get(pid, []), key=lambda pr: _clave_precio(pr, sector_preferido))
        if not ofertas:
            sin_precio.append(
                {
                    "producto_id": pid,
                    "nombre": prod.nombre_completo,
                    "cantidad": cant,
                    "url_alerta": f"/mis-alertas/?producto={pid}",
                }
            )
            analisis_productos.append(
                {
                    "producto_id": pid,
                    "nombre": prod.nombre_completo,
                    "cantidad": cant,
                    "disponible": False,
                    "mejor": None,
                    "segunda_opcion": None,
                    "mas_caro": None,
                    "promedio_unitario": 0,
                    "ahorro_vs_caro": 0,
                    "total_locales": 0,
                    "url_alerta": f"/mis-alertas/?producto={pid}",
                }
            )
            continue

        mejor = ofertas[0]
        caro = ofertas[-1]
        mejor_global_por_prod[pid] = mejor
        mas_caro_por_prod[pid] = caro
        promedio_unit = round(sum(o.precio_vigente for o in ofertas) / len(ofertas))
        ahorro_caro = max(0, (caro.precio_vigente - mejor.precio_vigente) * cant)

        segunda = None
        if len(ofertas) >= 2:
            o2 = ofertas[1]
            segunda = {
                "sucursal_id": o2.sucursal_id,
                "local": o2.sucursal.nombre_visible,
                "sector": o2.sucursal.sector,
                "precio_unitario": o2.precio_vigente,
                "subtotal": o2.precio_vigente * cant,
                "diferencia_unitaria": o2.precio_vigente - mejor.precio_vigente,
                "diferencia_subtotal": (o2.precio_vigente - mejor.precio_vigente) * cant,
            }

        analisis_productos.append(
            {
                "producto_id": pid,
                "nombre": prod.nombre_completo,
                "cantidad": cant,
                "disponible": True,
                "mejor": {
                    "sucursal_id": mejor.sucursal_id,
                    "local": mejor.sucursal.nombre_visible,
                    "sector": mejor.sucursal.sector,
                    "precio_unitario": mejor.precio_vigente,
                    "subtotal": mejor.precio_vigente * cant,
                    "es_oferta": mejor.es_oferta_activa,
                    "condiciones": list(mejor.etiquetas_condiciones),
                    "fecha_observacion": mejor.fecha_observacion.strftime("%d/%m/%Y") if mejor.fecha_observacion else "",
                },
                "segunda_opcion": segunda,
                "mas_caro": {
                    "local": caro.sucursal.nombre_visible,
                    "precio_unitario": caro.precio_vigente,
                    "subtotal": caro.precio_vigente * cant,
                },
                "promedio_unitario": promedio_unit,
                "ahorro_vs_caro": ahorro_caro,
                "total_locales": len(ofertas),
                "url_comparar": f"/producto/{pid}/",
            }
        )

    # 2. Ranking de comercios únicos (compatibilidad + selección de candidatos)
    total_solicitados = len(productos)
    ranking = []
    for sid, mapa_p in matriz.items():
        cubiertos_ids = [pid for pid in productos if pid in mapa_p]
        if not cubiertos_ids:
            continue
        subtotal = sum(mapa_p[pid].precio_vigente * cantidades[pid] for pid in cubiertos_ids)
        suc = sucursales_info[sid]
        ranking.append(
            {
                "sucursal_id": sid,
                "nombre": suc.nombre_visible,
                "direccion": suc.direccion,
                "sector": suc.sector,
                "url": f"/comercio/{sid}/",
                "cubiertos": len(cubiertos_ids),
                "total_solicitados": total_solicitados,
                "completo": len(cubiertos_ids) == total_solicitados,
                "total_clp": subtotal,
            }
        )
    ranking.sort(key=lambda r: (-r["cubiertos"], r["total_clp"]))
    mejor_unico = ranking[0] if ranking else None

    completos = [r for r in ranking if r["completo"]]
    ahorro_vs_max = 0
    if len(completos) >= 2:
        ahorro_vs_max = max(0, completos[-1]["total_clp"] - completos[0]["total_clp"])

    if not ranking:
        return {
            **vacio,
            "items_detalle": [{"producto_id": pid, "nombre": p.nombre_completo, "cantidad": cantidades[pid]} for pid, p in productos.items()],
            "analisis_productos": analisis_productos,
            "sin_precio": sin_precio,
        }

    # Pool de hasta 15 candidatos: ganadores individuales + top por cobertura/precio
    ganadores_sids = list(dict.fromkeys(pr.sucursal_id for pr in mejor_global_por_prod.values()))
    pool_sids = list(dict.fromkeys(ganadores_sids + [r["sucursal_id"] for r in ranking[:15]]))[:15]

    # 3. Escenarios de ruta: 1, 2, 3 locales y Ahorro máximo
    esc_uno = _evaluar_escenario(
        "uno",
        "1 local",
        [mejor_unico["sucursal_id"]],
        productos,
        cantidades,
        matriz,
        sucursales_info,
        sector_preferido,
        mejor_global_por_prod,
        mas_caro_por_prod,
    )

    esc_dos = None
    if len(pool_sids) >= 2:
        for par in combinations(pool_sids, 2):
            cand = _evaluar_escenario(
                "dos",
                "2 locales",
                list(par),
                productos,
                cantidades,
                matriz,
                sucursales_info,
                sector_preferido,
                mejor_global_por_prod,
                mas_caro_por_prod,
            )
            if esc_dos is None or (cand["cubiertos"] > esc_dos["cubiertos"]) or (
                cand["cubiertos"] == esc_dos["cubiertos"] and cand["total_clp"] < esc_dos["total_clp"]
            ):
                esc_dos = cand

    esc_tres = None
    if len(pool_sids) >= 3:
        for trio in combinations(pool_sids, 3):
            cand = _evaluar_escenario(
                "tres",
                "3 locales",
                list(trio),
                productos,
                cantidades,
                matriz,
                sucursales_info,
                sector_preferido,
                mejor_global_por_prod,
                mas_caro_por_prod,
            )
            if esc_tres is None or (cand["cubiertos"] > esc_tres["cubiertos"]) or (
                cand["cubiertos"] == esc_tres["cubiertos"] and cand["total_clp"] < esc_tres["total_clp"]
            ):
                esc_tres = cand

    esc_maximo = _evaluar_escenario(
        "maximo",
        "Ahorro máximo",
        list(dict.fromkeys(ganadores_sids)) or [mejor_unico["sucursal_id"]],
        productos,
        cantidades,
        matriz,
        sucursales_info,
        sector_preferido,
        mejor_global_por_prod,
        mas_caro_por_prod,
    )

    # Calcular ahorro vs escenario de 1 local y filtrar duplicados triviales de paradas
    escenarios = [esc_uno]
    if esc_dos and (esc_dos["cubiertos"] > esc_uno["cubiertos"] or esc_dos["total_clp"] < esc_uno["total_clp"]):
        escenarios.append(esc_dos)
    if esc_tres and (
        (esc_dos is None and (esc_tres["cubiertos"] > esc_uno["cubiertos"] or esc_tres["total_clp"] < esc_uno["total_clp"]))
        or (esc_dos is not None and (esc_tres["cubiertos"] > esc_dos["cubiertos"] or esc_tres["total_clp"] < esc_dos["total_clp"]))
    ):
        escenarios.append(esc_tres)
    if esc_maximo["paradas"] > 1 and (
        esc_maximo["cubiertos"] > escenarios[-1]["cubiertos"] or esc_maximo["total_clp"] < escenarios[-1]["total_clp"]
    ):
        escenarios.append(esc_maximo)

    for esc in escenarios:
        if esc["cubiertos"] >= esc_uno["cubiertos"]:
            esc["ahorro_vs_uno"] = max(0, esc_uno["total_clp"] - esc["total_clp"])

    # 4. Regla de "vale la pena desviarse" (umbral_desvio) respetando max_locales
    recomendado = esc_uno
    for esc in escenarios[1:]:
        if esc["paradas"] > max_locales:
            continue
        paradas_extra = max(1, esc["paradas"] - recomendado["paradas"])
        cubre_mas = esc["cubiertos"] > recomendado["cubiertos"]
        ahorro_extra = recomendado["total_clp"] - esc["total_clp"]
        if cubre_mas or (ahorro_extra > 0 and ahorro_extra >= umbral_desvio * paradas_extra):
            recomendado = esc

    recomendado["recomendado"] = True

    # Compatibilidad con clave antigua `mejor_combinacion_dos`
    mejor_dos_compat = None
    if esc_dos and len(esc_dos["locales"]) >= 2:
        l1, l2 = esc_dos["locales"][0], esc_dos["locales"][1]
        mejor_dos_compat = {
            "cubiertos": esc_dos["cubiertos"],
            "total_solicitados": total_solicitados,
            "total_clp": esc_dos["total_clp"],
            "local_1": {"nombre": l1["nombre"], "sector": l1["sector"], "items": l1["items"]},
            "local_2": {"nombre": l2["nombre"], "sector": l2["sector"], "items": l2["items"]},
        }

    items_detalle = [
        {"producto_id": pid, "nombre": prod.nombre_completo, "cantidad": cantidades[pid]}
        for pid, prod in productos.items()
    ]
    return {
        "items_detalle": items_detalle,
        "analisis_productos": analisis_productos,
        "sin_precio": sin_precio,
        "escenarios": escenarios,
        "escenario_recomendado_id": recomendado["id"],
        "configuracion": {"umbral_desvio": umbral_desvio, "max_locales": max_locales},
        # Claves heredadas
        "mejor_unico": mejor_unico,
        "ranking_unicos": ranking[:8],
        "mejor_combinacion_dos": mejor_dos_compat,
        "ahorro_vs_max": ahorro_vs_max,
    }
