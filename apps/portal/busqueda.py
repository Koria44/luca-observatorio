"""
Motor de búsqueda tolerante a tildes, mayúsculas y sinónimos chilenos (# REQ-04).

Funciona de manera idéntica en SQLite (local) y PostgreSQL (Supabase), expandiendo
sinónimos habituales en Chile ("porotos/frejoles", "palta/aguacate", "fideos/tallarines", etc.).
"""
import unicodedata

SINONIMOS_CHILE = {
    "porotos": ["porotos", "frejoles", "frijoles"],
    "frejoles": ["porotos", "frejoles"],
    "frijoles": ["porotos", "frejoles"],
    "palta": ["palta", "aguacate"],
    "aguacate": ["palta", "aguacate"],
    "fideos": ["tallarines", "espirales", "fideos"],
    "tallarines": ["tallarines", "espirales", "fideos"],
    "confort": ["papel higienico", "confort"],
    "pan": ["pan", "marraqueta", "hallulla", "molde"],
    "pollo": ["pollo", "trutro", "pechuga"],
    "carne": ["carne", "posta", "molida", "chuleta"],
    "cloro": ["cloro", "lejia"],
    "lejia": ["cloro", "lejia"],
    "remedio": ["paracetamol", "ibuprofeno", "loratadina"],
}


def quitar_tildes(texto: str) -> str:
    """Elimina diacríticos y normaliza a minúsculas para comparaciones tolerantes."""
    if not texto:
        return ""
    nfkd = unicodedata.normalize("NFKD", texto.strip().lower())
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def expandir_terminos(consulta: str) -> list[str]:
    """Devuelve la lista de términos normalizados incluyendo sinónimos locales."""
    base = quitar_tildes(consulta)
    if not base:
        return []
    palabras = [p for p in base.split() if len(p) >= 2]
    terminos = set(palabras)
    terminos.add(base)
    for p in palabras:
        if p in SINONIMOS_CHILE:
            terminos.update(SINONIMOS_CHILE[p])
    return list(terminos)


def coincide_producto(producto, consulta: str) -> bool:
    """Evalúa coincidencia tolerante contra nombre, marca, categoría y EAN."""
    if not consulta or not consulta.strip():
        return True
    texto_objetivo = quitar_tildes(
        f"{producto.nombre} {producto.marca.nombre} {producto.categoria.nombre} {producto.formato} {producto.codigo_barras or ''}"
    )
    terminos = expandir_terminos(consulta)
    return any(t in texto_objetivo for t in terminos)
